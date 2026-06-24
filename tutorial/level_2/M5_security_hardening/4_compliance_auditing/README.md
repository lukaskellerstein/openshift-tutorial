# L2-M5.4 --- Compliance & Auditing

**Level:** Practitioner
**Duration:** 30 min

## Overview

In Kubernetes, compliance scanning and auditing are entirely your problem --- you install third-party tools, write your own policies, and build audit log pipelines from scratch. OpenShift ships the **Compliance Operator**, which runs automated **OpenSCAP** scans against industry benchmarks (CIS, NIST, PCI-DSS) as native Kubernetes resources. Combined with OpenShift's built-in audit logging, you get a turnkey compliance posture that would take weeks to assemble on vanilla K8s.

In this lesson you will install the Compliance Operator, run automated CIS benchmark scans against your cluster, inspect and remediate findings, and configure audit log analysis to track who did what and when.

## Prerequisites

- Completed: L2-M5.2 (Pod Security & Admission)
- OpenShift cluster running (CRC or Developer Sandbox)
- Logged in as `kubeadmin` (cluster-admin privileges required)
- `oc` CLI installed and on PATH

## K8s Context

In vanilla Kubernetes, compliance scanning typically involves:

1. **Manual benchmarking** --- running tools like `kube-bench` on each node to check CIS Kubernetes benchmarks.
2. **No built-in audit infrastructure** --- you configure the API server's `--audit-policy-file` flag manually, then ship logs to an external SIEM.
3. **Policy engines bolted on** --- OPA Gatekeeper or Kyverno are installed separately to enforce compliance rules.
4. **Scan-as-code sprawl** --- each team builds their own scanning pipeline with Trivy, Anchore, or OpenSCAP containers.

There is no unified "compliance" abstraction in Kubernetes. You assemble the pieces yourself and hope they stay glued together.

## Concepts

### The Compliance Operator

The Compliance Operator brings automated, policy-driven compliance scanning into OpenShift as native CRDs:

| CRD | Purpose |
|-----|---------|
| **ComplianceScan** | A single scan against one profile (e.g., CIS Node benchmark) targeting either nodes or the platform. |
| **ComplianceSuite** | A collection of ComplianceScans bundled together --- run multiple profiles in one pass. |
| **ComplianceCheckResult** | The outcome of a single compliance rule (PASS, FAIL, MANUAL, NOT-APPLICABLE). |
| **ComplianceRemediation** | An auto-generated MachineConfig or other fix that can remediate a failed check. |
| **ScanSetting** | Reusable schedule and role configuration (which nodes to scan, how often). |
| **ScanSettingBinding** | Binds a Profile to a ScanSetting to create automated, recurring scans. |
| **Profile** | A compliance profile (CIS, NIST, PCI-DSS) shipped as content in the operator. |
| **TailoredProfile** | A custom profile that extends or restricts a base profile. |

### How OpenSCAP Fits In

The Compliance Operator uses **OpenSCAP** under the hood --- the same engine used by Red Hat for RHEL certification. Scans run as Pods on each targeted node, evaluate XCCDF rules, and report results as Kubernetes resources. You never interact with OpenSCAP directly; the operator abstracts it.

### CIS Benchmarks for OpenShift

CIS (Center for Internet Security) publishes hardening benchmarks for OpenShift. The Compliance Operator ships with these profiles:

- **ocp4-cis** --- CIS OpenShift benchmark (platform-level checks)
- **ocp4-cis-node** --- CIS node-level benchmark (worker and master node hardening)
- **ocp4-moderate** / **ocp4-high** --- NIST 800-53 profiles at moderate and high baselines
- **ocp4-pci-dss** --- PCI Data Security Standard checks

### Audit Logs

OpenShift's API server records every authenticated request in structured audit logs. Unlike vanilla K8s where you configure audit policies manually, OpenShift:

- Ships with a default audit policy that captures metadata for all requests and request bodies for sensitive resources.
- Stores audit logs on master nodes at `/var/log/kube-apiserver/` and `/var/log/openshift-apiserver/`.
- Integrates with OpenShift Logging to forward audit events to Loki or Elasticsearch for long-term retention and search.

### Why OpenShift Handles Compliance Differently

Enterprise customers face regulatory requirements (SOC 2, HIPAA, PCI-DSS, FedRAMP) that demand documented proof of compliance. OpenShift addresses this by:

- **Embedding scanning into the platform** --- no separate toolchain to maintain.
- **Providing auto-remediation** --- failed checks can generate MachineConfig patches that fix the issue automatically.
- **Using industry-standard content** --- SCAP profiles are the same ones auditors recognize.
- **Making results Kubernetes-native** --- `oc get compliancecheckresults` is easier to automate than parsing XML reports.

## Step-by-Step

### Step 1: Install the Compliance Operator

The Compliance Operator is available from OperatorHub. Install it cluster-wide.

```bash
# Create the namespace for the operator
oc apply -f manifests/compliance-operator-namespace.yaml
```

```bash
# Create the OperatorGroup and Subscription
oc apply -f manifests/compliance-operator-subscription.yaml
```

Wait for the operator to become ready:

```bash
oc get csv -n openshift-compliance -w
```

Expected output (wait until PHASE is `Succeeded`):

```
NAME                          DISPLAY               VERSION   PHASE
compliance-operator.v1.4.0    Compliance Operator    1.4.0     Succeeded
```

Verify the operator pods are running:

```bash
oc get pods -n openshift-compliance
```

Expected output:

```
NAME                                            READY   STATUS    RESTARTS   AGE
compliance-operator-6b8d5f7c4d-xk2rm            1/1     Running   0          2m
ocp4-openscap-pp-7f8d6b9c5-abc12                1/1     Running   0          90s
rhcos4-openscap-pp-5d6e7f8a9-def34               1/1     Running   0          90s
```

### Step 2: Explore Available Compliance Profiles

Once the operator is running, it populates the cluster with compliance profiles:

```bash
oc get profiles.compliance -n openshift-compliance
```

Expected output:

```
NAME                 AGE
ocp4-cis             3m
ocp4-cis-node        3m
ocp4-e8              3m
ocp4-high            3m
ocp4-high-node       3m
ocp4-moderate        3m
ocp4-moderate-node   3m
ocp4-nerc-cip        3m
ocp4-nerc-cip-node   3m
ocp4-pci-dss         3m
ocp4-pci-dss-node    3m
rhcos4-e8            3m
rhcos4-high          3m
rhcos4-moderate      3m
rhcos4-nerc-cip      3m
```

Inspect a specific profile to see what rules it contains:

```bash
oc get profile.compliance ocp4-cis -n openshift-compliance -o yaml | grep -A 5 "^  rules:"
```

You can also list all individual rules:

```bash
oc get rules.compliance -n openshift-compliance | head -20
```

### Step 3: Run a Single ComplianceScan

Start with a targeted scan against the CIS platform benchmark to see how it works:

```bash
oc apply -f manifests/compliance-scan-cis.yaml
```

Monitor the scan progress:

```bash
oc get compliancescan cis-platform-scan -n openshift-compliance -w
```

Expected output progression:

```
NAME                  PHASE       RESULT
cis-platform-scan     LAUNCHING   NOT-AVAILABLE
cis-platform-scan     RUNNING     NOT-AVAILABLE
cis-platform-scan     AGGREGATING NOT-AVAILABLE
cis-platform-scan     DONE        NON-COMPLIANT
```

A result of `NON-COMPLIANT` is normal --- very few clusters pass every CIS check out of the box. The value is in knowing *which* checks fail and prioritizing fixes.

### Step 4: Examine Scan Results

List the results from the scan:

```bash
oc get compliancecheckresults -n openshift-compliance \
  -l compliance.openshift.io/scan-name=cis-platform-scan
```

Filter to see only failures:

```bash
oc get compliancecheckresults -n openshift-compliance \
  -l compliance.openshift.io/scan-name=cis-platform-scan \
  --field-selector status.result=FAIL
```

Inspect a specific failed check for details:

```bash
# Pick any FAIL result from the output above and inspect it
oc get compliancecheckresult \
  ocp4-cis-api-server-encryption-provider-config \
  -n openshift-compliance -o yaml
```

The result includes:

- **description** --- what the check verifies
- **rationale** --- why it matters
- **severity** --- how critical the finding is (high, medium, low)
- **instructions** --- how to fix the issue manually

### Step 5: Run a Full ComplianceSuite

For a comprehensive scan, use a ComplianceSuite that combines platform and node checks:

```bash
oc apply -f manifests/compliance-suite-cis.yaml
```

Monitor the suite (it runs multiple scans in parallel):

```bash
oc get compliancesuite cis-full-suite -n openshift-compliance -w
```

Expected output:

```
NAME             PHASE   RESULT
cis-full-suite   RUNNING NOT-AVAILABLE
cis-full-suite   DONE    NON-COMPLIANT
```

View per-scan results within the suite:

```bash
oc get compliancescan -n openshift-compliance \
  -l compliance.openshift.io/suite=cis-full-suite
```

### Step 6: Set Up Recurring Scans with ScanSettingBinding

For production environments, you want scans to run on a schedule rather than manually. Use a ScanSettingBinding to bind a profile to a schedule:

```bash
oc apply -f manifests/scan-setting-binding.yaml
```

The default `ScanSetting` runs daily at 1:00 AM. Verify it exists:

```bash
oc get scansettings -n openshift-compliance
```

Expected output:

```
NAME              AGE
default           15m
default-auto-apply 15m
```

Check the binding:

```bash
oc get scansettingbinding cis-daily-scan -n openshift-compliance
```

The `default-auto-apply` ScanSetting goes further --- it automatically applies remediations. Use this only after reviewing what will be changed:

```bash
# List available remediations (do NOT apply blindly)
oc get complianceremediations -n openshift-compliance
```

### Step 7: Create a Tailored Profile

If the full CIS benchmark has checks that are not applicable to your environment, create a TailoredProfile that disables specific rules:

```bash
oc apply -f manifests/tailored-profile.yaml
```

Verify the tailored profile:

```bash
oc get tailoredprofiles -n openshift-compliance
```

Expected output:

```
NAME                STATE   
cis-tailored        READY
```

You can use this tailored profile in a ComplianceScan or ScanSettingBinding just like the built-in profiles.

### Step 8: Analyze Audit Logs

OpenShift audit logs capture every API request. On a CRC cluster, access them directly:

```bash
# Log in as kubeadmin and check audit log location
oc debug node/$(oc get nodes -o jsonpath='{.items[0].metadata.name}') -- \
  chroot /host ls /var/log/kube-apiserver/
```

Use the audit log analysis script to extract meaningful events:

```bash
# Run the audit log analysis script
bash scripts/audit-log-analysis.sh
```

You can also query audit events through the API (if OpenShift Logging is installed):

```bash
# Search for events by a specific user
oc debug node/$(oc get nodes -o jsonpath='{.items[0].metadata.name}') -- \
  chroot /host cat /var/log/kube-apiserver/audit.log | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        event = json.loads(line)
        if event.get('user', {}).get('username') == 'developer':
            print(f\"{event['requestReceivedTimestamp']} {event['verb']} {event['objectRef']['resource']}/{event.get('objectRef', {}).get('name', 'N/A')}\")
    except (json.JSONDecodeError, KeyError):
        pass
" 2>/dev/null | tail -20
```

### Step 9: Generate a Compliance Report

Extract scan results into a summary report:

```bash
# Summary of all check results across all scans
echo "=== Compliance Summary ==="
echo ""
echo "PASS:  $(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=PASS 2>/dev/null | wc -l)"
echo "FAIL:  $(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=FAIL 2>/dev/null | wc -l)"
echo "MANUAL: $(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=MANUAL 2>/dev/null | wc -l)"
echo "N/A:   $(oc get compliancecheckresults -n openshift-compliance --no-headers --field-selector status.result=NOT-APPLICABLE 2>/dev/null | wc -l)"
echo ""
echo "=== High Severity Failures ==="
oc get compliancecheckresults -n openshift-compliance \
  --field-selector status.result=FAIL \
  -o jsonpath='{range .items[?(@.status.severity=="high")]}{.metadata.name}{"\t"}{.status.severity}{"\t"}{.status.description}{"\n"}{end}' 2>/dev/null
```

## Verification

Confirm the lesson objectives are met:

```bash
# 1. Compliance Operator is running
echo "--- Operator Status ---"
oc get csv -n openshift-compliance -o jsonpath='{.items[0].status.phase}'
echo ""

# 2. Profiles are loaded
echo "--- Profiles Available ---"
oc get profiles.compliance -n openshift-compliance --no-headers | wc -l
echo " profiles loaded"

# 3. At least one scan has completed
echo "--- Scan Status ---"
oc get compliancescan -n openshift-compliance

# 4. Results are available
echo "--- Check Results ---"
oc get compliancecheckresults -n openshift-compliance --no-headers | wc -l
echo " check results available"

# 5. ScanSettingBinding is configured
echo "--- Scheduled Scans ---"
oc get scansettingbinding -n openshift-compliance
```

Expected verification output:

```
--- Operator Status ---
Succeeded
--- Profiles Available ---
15 profiles loaded
--- Scan Status ---
NAME                  PHASE   RESULT
cis-platform-scan     DONE    NON-COMPLIANT
cis-node-master       DONE    NON-COMPLIANT
cis-node-worker       DONE    NON-COMPLIANT
--- Check Results ---
187 check results available
--- Scheduled Scans ---
NAME             PROFILES                   SCANSETTINGS
cis-daily-scan   ["ocp4-cis","ocp4-cis-node"]   default
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Compliance scanning | Install `kube-bench` or OpenSCAP containers manually | Compliance Operator with CRD-based scanning |
| Benchmark profiles | Download and manage XCCDF/SCAP content yourself | Profiles ship with the operator, versioned and maintained by Red Hat |
| Scan scheduling | Build your own CronJob or CI pipeline | `ScanSettingBinding` with built-in cron scheduling |
| Remediation | Read the report, fix manually | `ComplianceRemediation` CRDs can auto-generate and apply MachineConfigs |
| Results format | XML/HTML reports on a filesystem | Kubernetes CRDs queryable with `oc get` and standard label selectors |
| Audit logs | Configure `--audit-policy-file` on API server manually | Pre-configured audit policy, logs available on master nodes |
| Audit log forwarding | Set up Fluentd/Vector pipeline yourself | OpenShift Logging operator with `ClusterLogForwarder` for audit logs |
| CIS benchmark content | Generic "CIS Kubernetes Benchmark" | OpenShift-specific "CIS OpenShift Benchmark" with RHCOS checks |
| Tailored profiles | Edit XCCDF XML files | `TailoredProfile` CRD to customize profiles declaratively |
| Integration with policy engines | Separate OPA/Kyverno installation | Can complement Compliance Operator with Gatekeeper (covered in L2-M5.2) |

## Key Takeaways

- The **Compliance Operator** turns compliance scanning from an external toolchain problem into a native Kubernetes workflow --- `oc apply` a scan, `oc get` the results.
- **CIS benchmarks for OpenShift** go beyond generic Kubernetes benchmarks by including RHCOS node hardening and OpenShift-specific platform checks.
- **Auto-remediation** via `ComplianceRemediation` CRDs can generate MachineConfig patches, but always review before applying --- some remediations may affect workload behavior.
- OpenShift's **built-in audit logging** captures every API request with a pre-configured policy, eliminating a common compliance gap in vanilla Kubernetes clusters.
- **Recurring scans** via `ScanSettingBinding` ensure compliance drift is detected automatically, not just at audit time.

## Troubleshooting

### Scan Pods Stuck in Pending

```bash
# Check if nodes have enough resources for scan pods
oc get pods -n openshift-compliance -o wide | grep -i pending

# On CRC, resources are limited --- scale down other workloads if needed
oc get pods --all-namespaces --field-selector status.phase=Running --no-headers | wc -l
```

### "No profiles found" After Operator Install

The operator needs a minute to parse and load SCAP content. Wait for the profile-parser pods to complete:

```bash
oc get pods -n openshift-compliance | grep pp
# Wait until these pods show Completed or Running status
```

### ComplianceScan Shows DONE but No Results

Check the scan pod logs for errors:

```bash
oc logs -n openshift-compliance \
  $(oc get pods -n openshift-compliance -l compliance.openshift.io/scan-name=cis-platform-scan -o name | head -1)
```

### Auto-Remediation Applied Unexpected Changes

If a remediation caused issues, pause and revert:

```bash
# List applied remediations
oc get complianceremediations -n openshift-compliance \
  --field-selector status.applicationState=Applied

# To unapply a remediation, set apply to false
oc patch complianceremediation <name> -n openshift-compliance \
  --type merge -p '{"spec":{"apply":false}}'
```

## Cleanup

```bash
# Delete the ScanSettingBinding (stops scheduled scans)
oc delete scansettingbinding cis-daily-scan -n openshift-compliance

# Delete the TailoredProfile
oc delete tailoredprofile cis-tailored -n openshift-compliance

# Delete the ComplianceSuite (also deletes child ComplianceScans)
oc delete compliancesuite cis-full-suite -n openshift-compliance

# Delete the standalone ComplianceScan
oc delete compliancescan cis-platform-scan -n openshift-compliance

# Delete all check results and remediations
oc delete compliancecheckresults --all -n openshift-compliance
oc delete complianceremediations --all -n openshift-compliance

# (Optional) Remove the Compliance Operator entirely
oc delete subscription compliance-operator -n openshift-compliance
oc delete csv -n openshift-compliance --all
oc delete operatorgroup compliance-operator -n openshift-compliance
oc delete namespace openshift-compliance
```

## Next Steps

In **L2-M6.1 --- OpenShift Dev Spaces (Eclipse Che)**, you will explore cloud-based development environments running inside OpenShift. Dev Spaces provides pre-configured, reproducible workspaces using Devfiles, eliminating "works on my machine" problems and bringing the IDE into the cluster.
