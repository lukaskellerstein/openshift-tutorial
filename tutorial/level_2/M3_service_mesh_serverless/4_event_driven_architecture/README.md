# L2-M3.4 — Event-Driven Architecture

**Level:** Practitioner
**Duration:** 45 min

## Overview

In Kubernetes, building event-driven systems means integrating external tools like NATS, RabbitMQ, or Kafka with custom glue code to wire producers to consumers. OpenShift Serverless (Knative Eventing) provides a declarative, platform-native event routing layer: Brokers collect events, Triggers filter and route them, and CloudEvents provide a standard envelope format. In this lesson you will build a complete event-driven flow where events flow from a source through a broker, get filtered by triggers, and land on Knative Services that scale to zero when idle.

## Prerequisites

- Completed: L2-M3.3 (OpenShift Serverless / Knative Serving)
- OpenShift cluster running (CRC or Developer Sandbox)
- OpenShift Serverless operator installed with Knative Serving and Knative Eventing enabled
- `oc` CLI installed and authenticated
- Familiarity with Knative Services (covered in L2-M3.3)

## K8s Context

In vanilla Kubernetes, event-driven architecture requires assembling multiple pieces yourself:

- **Message broker**: Deploy Kafka, RabbitMQ, or NATS into the cluster.
- **Consumer glue**: Write custom code or use frameworks (Spring Cloud Stream, Dapr) to connect consumers to topics/queues.
- **Scaling**: Configure KEDA or custom HPA policies to scale consumers based on queue depth.
- **Event format**: Choose your own serialization (JSON, Avro, Protobuf) with no standard envelope.

There is no built-in Kubernetes primitive for "when event X happens, deliver it to service Y." You build all the plumbing yourself.

## Concepts

### Knative Eventing Architecture

Knative Eventing introduces a declarative event routing layer with four core primitives:

**Broker** -- An event mesh that receives CloudEvents and holds them for delivery. Think of it as an in-cluster event bus. The default implementation uses an in-memory channel, but production deployments can back it with Kafka.

**Trigger** -- A filter rule attached to a Broker. Each Trigger specifies which events it wants (by CloudEvents attributes like `type` and `source`) and which subscriber receives matching events. Multiple Triggers can attach to the same Broker, enabling fan-out routing.

**Channel** -- A durable, ordered event delivery mechanism (similar to a Kafka topic or NATS subject). Channels are lower-level than Brokers -- use them when you need point-to-point or pipeline-style delivery rather than content-based routing.

**Subscription** -- Connects a Channel to a subscriber service. Where Triggers do content-based filtering, Subscriptions deliver everything from a Channel to a subscriber.

### CloudEvents

CloudEvents is a CNCF specification that defines a standard envelope for event data. Every Knative event is a CloudEvent with mandatory attributes:

| Attribute | Description | Example |
|-----------|-------------|---------|
| `specversion` | CloudEvents version | `1.0` |
| `type` | Event type identifier | `dev.knative.samples.ping` |
| `source` | Event origin URI | `/apis/v1/namespaces/demo/pingsources/heartbeat` |
| `id` | Unique event ID | `a1b2c3d4-...` |
| `time` | Timestamp | `2026-06-24T10:00:00Z` |

This standard format means any CloudEvents-compatible producer can send to any Knative Broker, and any consumer can parse the envelope without custom deserialization code.

### Event Sources

Knative provides built-in event sources that generate CloudEvents from external systems:

- **PingSource** -- Sends events on a cron schedule (useful for testing and scheduled jobs).
- **ApiServerSource** -- Watches Kubernetes API server events (pod creation, deletion, etc.).
- **KafkaSource** -- Consumes messages from Apache Kafka topics and wraps them as CloudEvents.
- **SinkBinding** -- Injects sink (destination) information into any workload, turning it into an event source.

### Why OpenShift Does This

OpenShift Serverless (Knative Eventing) solves three problems that K8s leaves to you:

1. **Standard event format**: CloudEvents eliminate custom serialization and parsing.
2. **Declarative routing**: Triggers replace hand-coded message routing logic.
3. **Scale-to-zero consumers**: Services receiving events scale down when no events flow, saving resources. When events arrive, they scale up automatically.

## Step-by-Step

### Step 1: Create the Project and Verify Knative Eventing

Create a dedicated project for the event-driven demo and confirm that Knative Eventing is operational.

```bash
oc new-project event-driven-demo
```

Verify that Knative Eventing is ready:

```bash
oc get knativeeventing knative-eventing -n knative-eventing
```

Expected output:

```
NAME               VERSION   READY   REASON
knative-eventing   1.12.4    True
```

If Knative Eventing is not installed, install it via the Web Console: Operators > Installed Operators > OpenShift Serverless > Knative Eventing tab > Create KnativeEventing (accept defaults).

### Step 2: Deploy the Event Display Service

Deploy a Knative Service that logs every CloudEvent it receives. This acts as the event consumer for our flow.

```bash
oc apply -f manifests/event-display-ksvc.yaml
```

```yaml
# manifests/event-display-ksvc.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: event-display
  labels:
    app: event-display
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "5"
    spec:
      containers:
        - image: gcr.io/knative-releases/knative.dev/eventing/cmd/event_display
          name: event-display
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
          ports:
            - containerPort: 8080
              protocol: TCP
```

Verify the service is ready:

```bash
oc get ksvc event-display
```

Expected output:

```
NAME            URL                                                         LATESTCREATED         LATESTREADY           READY   REASON
event-display   https://event-display-event-driven-demo.apps-crc.testing    event-display-00001   event-display-00001   True
```

The service will scale to zero since no events are flowing yet.

### Step 3: Create a Broker

Create a Broker in the project. This is the central event bus that receives events and distributes them via Triggers.

```bash
oc apply -f manifests/default-broker.yaml
```

```yaml
# manifests/default-broker.yaml
apiVersion: eventing.knative.dev/v1
kind: Broker
metadata:
  name: default
  labels:
    app: event-broker
    tutorial-level: "2"
    tutorial-module: "M3"
  annotations:
    eventing.knative.dev/broker.class: MTChannelBasedBroker
spec: {}
```

Verify the Broker is ready:

```bash
oc get broker default
```

Expected output:

```
NAME      URL                                                                               AGE   READY   REASON
default   http://broker-ingress.knative-eventing.svc.cluster.local/event-driven-demo/default   10s   True
```

The Broker URL is the address where event sources send CloudEvents to.

### Step 4: Create Triggers for Event Routing

Create two Triggers to demonstrate content-based routing. The first catches all events; the second filters for a specific event type.

Deploy a second consumer service first -- a "logger" that only receives critical events:

```bash
oc apply -f manifests/critical-logger-ksvc.yaml
```

```yaml
# manifests/critical-logger-ksvc.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: critical-logger
  labels:
    app: critical-logger
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "3"
    spec:
      containers:
        - image: gcr.io/knative-releases/knative.dev/eventing/cmd/event_display
          name: critical-logger
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 200m
              memory: 128Mi
          ports:
            - containerPort: 8080
              protocol: TCP
```

Now create the Triggers:

```bash
oc apply -f manifests/trigger-all-events.yaml
oc apply -f manifests/trigger-critical-only.yaml
```

```yaml
# manifests/trigger-all-events.yaml -- routes ALL events to event-display
apiVersion: eventing.knative.dev/v1
kind: Trigger
metadata:
  name: all-events
  labels:
    app: event-routing
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  broker: default
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: event-display
```

```yaml
# manifests/trigger-critical-only.yaml -- routes only "critical" events
apiVersion: eventing.knative.dev/v1
kind: Trigger
metadata:
  name: critical-only
  labels:
    app: event-routing
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  broker: default
  filter:
    attributes:
      type: com.example.critical
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: critical-logger
```

Verify both Triggers are ready:

```bash
oc get triggers
```

Expected output:

```
NAME             BROKER    SUBSCRIBER_URI                                            AGE   READY   REASON
all-events       default   http://event-display.event-driven-demo.svc.cluster.local  10s   True
critical-only    default   http://critical-logger.event-driven-demo.svc.cluster.local 10s   True
```

The `all-events` Trigger has no filter -- it receives every event. The `critical-only` Trigger only receives events with `type: com.example.critical`.

### Step 5: Create a PingSource (Cron-Based Event Source)

Create a PingSource that sends a CloudEvent to the Broker every 30 seconds. This simulates an event producer.

```bash
oc apply -f manifests/ping-source.yaml
```

```yaml
# manifests/ping-source.yaml
apiVersion: sources.knative.dev/v1
kind: PingSource
metadata:
  name: heartbeat
  labels:
    app: event-source
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  schedule: "*/1 * * * *"
  contentType: "application/json"
  data: '{"message": "heartbeat ping", "severity": "info"}'
  sink:
    ref:
      apiVersion: eventing.knative.dev/v1
      kind: Broker
      name: default
```

Verify the PingSource is ready:

```bash
oc get pingsources
```

Expected output:

```
NAME        SINK                                                                            SCHEDULE      AGE   READY   REASON
heartbeat   http://broker-ingress.knative-eventing.svc.cluster.local/event-driven-demo/default   */1 * * * *   10s   True
```

Wait about 60 seconds for the first event to fire, then check the event-display logs:

```bash
oc logs -l serving.knative.dev/service=event-display -c event-display --tail=20
```

Expected output:

```
☁️  cloudevents.Event
Context Attributes,
  specversion: 1.0
  type: dev.knative.sources.ping
  source: /apis/v1/namespaces/event-driven-demo/pingsources/heartbeat
  id: 8a3f2b1c-...
  time: 2026-06-24T10:01:00.000Z
  datacontenttype: application/json
Data,
  {"message": "heartbeat ping", "severity": "info"}
```

Notice that only `event-display` received this event. The `critical-logger` did NOT receive it because the PingSource sends events with type `dev.knative.sources.ping`, not `com.example.critical`.

### Step 6: Send a Custom CloudEvent to Test Filtering

Send a custom CloudEvent with type `com.example.critical` to demonstrate that the `critical-only` Trigger routes it to the `critical-logger`.

First, create a pod that can send events from inside the cluster:

```bash
oc run curl-sender --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  --restart=Never \
  --command -- sleep 3600
```

Wait for the pod to be running:

```bash
oc wait --for=condition=Ready pod/curl-sender --timeout=60s
```

Send a critical event to the Broker:

```bash
oc exec curl-sender -- curl -s -v \
  "http://broker-ingress.knative-eventing.svc.cluster.local/event-driven-demo/default" \
  -H "Ce-Id: custom-001" \
  -H "Ce-Specversion: 1.0" \
  -H "Ce-Type: com.example.critical" \
  -H "Ce-Source: /manual/test" \
  -H "Content-Type: application/json" \
  -d '{"alert": "disk usage above 90%", "severity": "critical", "host": "worker-01"}'
```

Expected output (stderr):

```
< HTTP/1.1 202 Accepted
```

Now check both services. The event-display should have the event (it receives everything):

```bash
oc logs -l serving.knative.dev/service=event-display -c event-display --tail=10
```

And the critical-logger should also have it (because `type` matches `com.example.critical`):

```bash
oc logs -l serving.knative.dev/service=critical-logger -c critical-logger --tail=10
```

Expected output for critical-logger:

```
☁️  cloudevents.Event
Context Attributes,
  specversion: 1.0
  type: com.example.critical
  source: /manual/test
  id: custom-001
  datacontenttype: application/json
Data,
  {"alert": "disk usage above 90%", "severity": "critical", "host": "worker-01"}
```

This demonstrates fan-out: one event, two subscribers, each receiving it independently based on their filter rules.

### Step 7: Create an ApiServerSource

Create an ApiServerSource that watches for Pod events in the project and forwards them to the Broker. This is a real-world use case: reacting to Kubernetes lifecycle events.

First, create a ServiceAccount with the necessary RBAC permissions:

```bash
oc apply -f manifests/event-sa-rbac.yaml
```

```yaml
# manifests/event-sa-rbac.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: event-watcher
  labels:
    app: event-watcher
    tutorial-level: "2"
    tutorial-module: "M3"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: event-watcher-role
  labels:
    app: event-watcher
    tutorial-level: "2"
    tutorial-module: "M3"
rules:
  - apiGroups:
      - ""
    resources:
      - events
    verbs:
      - get
      - list
      - watch
  - apiGroups:
      - ""
    resources:
      - pods
    verbs:
      - get
      - list
      - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: event-watcher-binding
  labels:
    app: event-watcher
    tutorial-level: "2"
    tutorial-module: "M3"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: event-watcher-role
subjects:
  - kind: ServiceAccount
    name: event-watcher
```

Now create the ApiServerSource:

```bash
oc apply -f manifests/api-server-source.yaml
```

```yaml
# manifests/api-server-source.yaml
apiVersion: sources.knative.dev/v1
kind: ApiServerSource
metadata:
  name: pod-watcher
  labels:
    app: event-source
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  serviceAccountName: event-watcher
  mode: Resource
  resources:
    - apiVersion: v1
      kind: Pod
  sink:
    ref:
      apiVersion: eventing.knative.dev/v1
      kind: Broker
      name: default
```

Verify it is ready:

```bash
oc get apiserversources
```

Expected output:

```
NAME          SINK                                                                            AGE   READY   REASON
pod-watcher   http://broker-ingress.knative-eventing.svc.cluster.local/event-driven-demo/default   10s   True
```

Now trigger a pod event by creating and deleting a test pod:

```bash
oc run test-event-pod --image=registry.access.redhat.com/ubi9/ubi-minimal:latest \
  --restart=Never --command -- echo "hello"
```

Wait a moment, then check the event-display logs for the pod lifecycle event:

```bash
oc logs -l serving.knative.dev/service=event-display -c event-display --tail=30
```

You should see CloudEvents with type `dev.knative.apiserver.resource.add` containing the Pod spec as the data payload. Delete the test pod:

```bash
oc delete pod test-event-pod
```

This generates a `dev.knative.apiserver.resource.delete` event.

### Step 8: Set Up a Channel and Subscription Pipeline

Create a Channel-based pipeline to demonstrate the alternative to Broker/Trigger. Channels provide ordered, point-to-point delivery -- useful for sequential processing pipelines.

```bash
oc apply -f manifests/channel.yaml
oc apply -f manifests/subscription.yaml
```

```yaml
# manifests/channel.yaml
apiVersion: messaging.knative.dev/v1
kind: Channel
metadata:
  name: processing-pipeline
  labels:
    app: event-pipeline
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  channelTemplate:
    apiVersion: messaging.knative.dev/v1
    kind: InMemoryChannel
```

```yaml
# manifests/subscription.yaml
apiVersion: messaging.knative.dev/v1
kind: Subscription
metadata:
  name: pipeline-to-display
  labels:
    app: event-pipeline
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  channel:
    apiVersion: messaging.knative.dev/v1
    kind: Channel
    name: processing-pipeline
  subscriber:
    ref:
      apiVersion: serving.knative.dev/v1
      kind: Service
      name: event-display
```

Verify:

```bash
oc get channels
oc get subscriptions
```

Expected output:

```
NAME                  URL                                                                     AGE   READY
processing-pipeline   http://processing-pipeline-kn-channel.event-driven-demo.svc.cluster.local   10s   True

NAME                  AGE   READY   REASON
pipeline-to-display   10s   True
```

Send an event directly to the Channel (bypassing the Broker):

```bash
oc exec curl-sender -- curl -s -v \
  "http://processing-pipeline-kn-channel.event-driven-demo.svc.cluster.local" \
  -H "Ce-Id: channel-001" \
  -H "Ce-Specversion: 1.0" \
  -H "Ce-Type: com.example.pipeline.step1" \
  -H "Ce-Source: /pipeline/input" \
  -H "Content-Type: application/json" \
  -d '{"order_id": "ORD-1234", "status": "received"}'
```

Check event-display for the event:

```bash
oc logs -l serving.knative.dev/service=event-display -c event-display --tail=10
```

### Step 9: Explore KafkaSource (Conceptual + Manifest)

In production, the most common event source is Apache Kafka. The KafkaSource controller connects Kafka topics to the Knative event mesh. This requires the `KnativeKafka` custom resource to be enabled on the cluster.

Below is a reference manifest for connecting to a Kafka cluster. Do NOT apply this unless you have a running Kafka instance (for example, one managed by the Strimzi operator from L2-M2.3):

```yaml
# manifests/kafka-source.yaml -- REFERENCE ONLY (requires a Kafka cluster)
apiVersion: sources.knative.dev/v1beta1
kind: KafkaSource
metadata:
  name: order-events
  labels:
    app: kafka-source
    tutorial-level: "2"
    tutorial-module: "M3"
spec:
  consumerGroup: knative-consumer-group
  bootstrapServers:
    - my-kafka-cluster-kafka-bootstrap.kafka.svc.cluster.local:9092
  topics:
    - orders
  sink:
    ref:
      apiVersion: eventing.knative.dev/v1
      kind: Broker
      name: default
```

Key points about KafkaSource:

- Each Kafka message becomes a CloudEvent with `type: dev.knative.kafka.event`.
- The `consumerGroup` prevents duplicate processing across replicas.
- Kafka provides durable, high-throughput event delivery compared to the in-memory default.
- Enable it by creating a `KnativeKafka` CR in the `knative-eventing` namespace with `spec.channel.enabled: true` and `spec.source.enabled: true`.

## Verification

Run these checks to confirm the full event-driven flow is working:

```bash
# 1. All sources are ready
oc get pingsources,apiserversources

# 2. Broker is ready
oc get broker default

# 3. Triggers are ready and routing correctly
oc get triggers

# 4. Channel and Subscription are ready
oc get channels,subscriptions

# 5. Knative Services are deployed
oc get ksvc

# 6. event-display received PingSource events
oc logs -l serving.knative.dev/service=event-display -c event-display --tail=5

# 7. critical-logger received only critical events (or no events if none were sent)
oc logs -l serving.knative.dev/service=critical-logger -c critical-logger --tail=5
```

You can also observe the flow in the OpenShift Web Console:

1. Switch to the **Developer** perspective.
2. Navigate to the **Topology** view.
3. You should see the event sources, Broker, and Knative Services with arrows showing the event flow.
4. The Knative Services will show as scaled-to-zero (hollow circles) when no events are flowing, and scale up (filled circles) when events arrive.

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift (Knative Eventing) |
|--------|-----------|-----------|
| Event bus | Deploy Kafka/NATS/RabbitMQ manually | Broker CR -- one YAML to create an event bus |
| Event format | Choose your own (JSON, Avro, etc.) | CloudEvents standard -- universal envelope |
| Routing | Write consumer code with topic filters | Trigger CR -- declarative content-based routing |
| Fan-out | Application-level pub/sub logic | Multiple Triggers on one Broker -- automatic |
| Event sources | Custom producers with client libraries | Built-in PingSource, ApiServerSource, KafkaSource |
| Consumer scaling | KEDA / custom HPA | Scale-to-zero built into Knative Services |
| Point-to-point | Queue per consumer | Channel + Subscription CRs |
| K8s event integration | Custom controllers watching the API | ApiServerSource -- declare what to watch |
| Observability | Instrument each service | CloudEvents tracing headers built in |
| Installation | Install and manage each component | OpenShift Serverless operator manages everything |

## Key Takeaways

- **Brokers and Triggers** provide declarative, content-based event routing without writing routing code. Triggers filter on CloudEvents attributes (`type`, `source`) to deliver events to the right services.
- **CloudEvents** is a CNCF standard envelope format. All Knative event sources produce CloudEvents, making producers and consumers interoperable without custom serialization.
- **Channels and Subscriptions** offer ordered, point-to-point event delivery for pipeline-style processing, complementing the fan-out model of Brokers and Triggers.
- **Event sources** (PingSource, ApiServerSource, KafkaSource) bridge external systems into the Knative event mesh, converting native messages into CloudEvents automatically.
- **Scale-to-zero** applies to event consumers too -- Knative Services that receive events via Triggers scale down when idle and spin up when events arrive, saving resources on CRC's limited capacity.

## Troubleshooting

**Trigger shows READY=False with "BrokerDoesNotExist"**
The Trigger references a Broker that does not exist in the current namespace. Verify with `oc get brokers` and ensure the Trigger's `spec.broker` field matches.

**Events are not reaching the subscriber**
Check the Trigger filter. If you specified `filter.attributes.type: com.example.critical` but the event has type `dev.knative.sources.ping`, the Trigger will not match. Remove the filter block to receive all events and narrow it down.

**PingSource is READY but no events appear**
The schedule uses cron syntax. `*/1 * * * *` fires every minute. Wait at least 60 seconds and check the logs again. Also verify the Broker URL is correct: `oc get pingsources -o yaml | grep sinkUri`.

**ApiServerSource shows permission errors**
The ServiceAccount needs explicit RBAC to watch the resources specified in the source. Check `oc describe apiserversource pod-watcher` for error messages and verify the Role/RoleBinding grants `get`, `list`, `watch` on the target resources.

**Knative Service stays at zero replicas even when events flow**
If the Broker is not ready, events are dropped silently. Verify `oc get broker default` shows READY=True. Also check the activator component: `oc get pods -n knative-serving -l app=activator`.

**"No matching channel implementation" error on Channel creation**
The InMemoryChannel is the default. If it is not available, check that the Knative Eventing installation completed successfully: `oc get knativeeventing -n knative-eventing`.

## Cleanup

```bash
# Delete event sources
oc delete pingsource heartbeat
oc delete apiserversource pod-watcher

# Delete triggers
oc delete trigger all-events critical-only

# Delete broker
oc delete broker default

# Delete channel and subscription
oc delete subscription pipeline-to-display
oc delete channel processing-pipeline

# Delete Knative services
oc delete ksvc event-display critical-logger

# Delete RBAC resources
oc delete rolebinding event-watcher-binding
oc delete role event-watcher-role
oc delete sa event-watcher

# Delete utility pod
oc delete pod curl-sender --ignore-not-found

# Delete test pod (if still present)
oc delete pod test-event-pod --ignore-not-found

# Delete the project
oc delete project event-driven-demo
```

## Next Steps

In **L2-M4.1 -- Egress & Ingress Control**, you will learn how to control outbound traffic from OpenShift workloads using EgressFirewall, EgressIP, and EgressRouter. This is critical for production event-driven architectures where services need to communicate with external systems (like Kafka clusters or third-party APIs) through controlled egress points.
