# L1-M2.2 — Authentication & OAuth

**Level:** Foundations
**Duration:** 30 min

## Overview

OpenShift ships with a built-in OAuth server that handles user authentication out of the box -- something Kubernetes leaves entirely to you. In this lesson you will learn how OpenShift's OAuth server works, how to configure identity providers (with HTPasswd as a hands-on example), and how `oc login` and tokens differ from the raw kubeconfig + ServiceAccount token workflow you know from Kubernetes.

## Prerequisites

- Completed: L1-M2.1 (Projects vs Namespaces)
- OpenShift cluster running (CRC or Developer Sandbox)
- `oc` CLI installed and on PATH
- `htpasswd` utility installed (`httpd-tools` on RHEL/Fedora, `apache2-utils` on Debian/Ubuntu, pre-installed on macOS)

## K8s Context

In vanilla Kubernetes, there is **no built-in user authentication system**. The API server supports several authentication strategies -- client certificates, bearer tokens, OIDC, webhook token authentication -- but you must configure and operate them yourself. Most production K8s clusters delegate authentication to an external identity provider via OIDC, or rely on cloud-provider IAM (EKS IRSA, GKE Workload Identity, etc.).

For service-to-service communication, Kubernetes uses **ServiceAccount tokens** -- JWTs mounted into pods automatically. These are the only "users" Kubernetes truly manages natively.

The typical developer experience in K8s looks like this:

1. An admin generates a kubeconfig with client certificates or an OIDC token.
2. The developer sets `KUBECONFIG` or merges contexts into `~/.kube/config`.
3. There is no `kubectl login` command -- authentication is entirely kubeconfig-driven.

## Concepts

### OpenShift's Built-in OAuth Server

OpenShift runs an OAuth 2.0 server as a core platform component. This server:

- Provides a `/login` endpoint for interactive authentication
- Issues **OAuth access tokens** (not client certificates) for API access
- Supports pluggable **identity providers** (IdPs) -- you choose how users prove their identity
- Integrates with the Web Console -- the login page you see is the OAuth server's login form

When you run `oc login`, the CLI contacts the OAuth server, authenticates via your configured identity provider, receives an OAuth access token, and writes it to your kubeconfig. This is fundamentally different from the K8s approach where kubeconfig is pre-populated by an admin.

### Identity Providers

OpenShift supports multiple identity providers, configured via the cluster-wide **OAuth** custom resource (`oauth/cluster`):

| Identity Provider | Use Case |
|---|---|
| **HTPasswd** | Small teams, labs, demos. Users stored in a flat file. |
| **LDAP** | Enterprise environments with existing Active Directory or OpenLDAP. |
| **GitHub / GitLab** | Developer-centric organizations using social login. |
| **OpenID Connect** | Integrate with any OIDC provider (Keycloak, Okta, Azure AD, Google). |
| **Basic Authentication** | Delegates to a remote HTTP endpoint. |
| **Request Header** | Trusts a front-end proxy (X-Remote-User header). |
| **Keystone** | OpenStack environments. |

You can configure **multiple providers simultaneously** -- the login page will show all of them and let the user choose.

### OAuth Tokens vs Kubeconfig

In Kubernetes, your kubeconfig might contain a client certificate, a bearer token, or an exec-based credential plugin. In OpenShift:

- `oc login` authenticates via OAuth and stores a **time-limited token** in `~/.kube/config`
- Tokens expire (default: 24 hours) -- you must re-authenticate
- You can view your token with `oc whoami -t`
- You can list all active tokens with `oc get oauthaccesstokens` (as cluster-admin)
- Tokens can be revoked without rotating certificates

### The HTPasswd Identity Provider

HTPasswd is the simplest identity provider -- it stores usernames and bcrypt-hashed passwords in a file, which is then stored as a Secret in the `openshift-config` namespace. It is ideal for:

- Local development with CRC
- Small teams without enterprise identity infrastructure
- Labs and tutorials (like this one)

The workflow is:

1. Create an htpasswd file with users and passwords
2. Store it as a Secret in `openshift-config`
3. Update the OAuth cluster resource to reference it
4. The OAuth server picks up the change and starts accepting those credentials

## Step-by-Step

### Step 1: Explore the Current Authentication Setup

Log in as `kubeadmin` (cluster-admin) and examine the existing OAuth configuration:

```bash
# Log in as cluster admin (password from crc start output)
oc login -u kubeadmin -p <your-kubeadmin-password> https://api.crc.testing:6443

# View the cluster OAuth resource
oc get oauth cluster -o yaml
```

Expected output (CRC default -- no identity providers configured beyond the initial setup):

```yaml
apiVersion: config.openshift.io/v1
kind: OAuth
metadata:
  name: cluster
spec: {}
```

On a fresh CRC install, the `kubeadmin` user is a special bootstrapping account -- it is not backed by any identity provider. It is meant to be removed once real identity providers are configured.

### Step 2: Check Your Current Identity

```bash
# Who am I?
oc whoami
```

```
kubeadmin
```

```bash
# What is my token?
oc whoami -t
```

```
sha256~xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

```bash
# What server am I connected to?
oc whoami --show-server
```

```
https://api.crc.testing:6443
```

```bash
# Show the full context (similar to kubectl config current-context)
oc whoami --show-context
```

### Step 3: Create an HTPasswd File with Users

Use the `htpasswd` utility to create a file with two users:

```bash
# Create a new htpasswd file with the first user
htpasswd -c -B -b /tmp/htpasswd-users admin redhat123

# Add a second user (-B uses bcrypt hashing)
htpasswd -B -b /tmp/htpasswd-users developer developer123

# Add a third user
htpasswd -B -b /tmp/htpasswd-users viewer viewer123
```

Flags explained:
- `-c` -- create a new file (only for the first user)
- `-B` -- use bcrypt hashing (recommended; OpenShift requires bcrypt or MD5)
- `-b` -- take the password from the command line (instead of prompting)

Verify the file was created:

```bash
cat /tmp/htpasswd-users
```

Expected output (hashes will differ):

```
admin:$2y$05$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
developer:$2y$05$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
viewer:$2y$05$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 4: Create the HTPasswd Secret in OpenShift

Store the htpasswd file as a Secret in the `openshift-config` namespace:

```bash
# Create the secret from the htpasswd file
oc create secret generic htpasswd-secret \
  --from-file=htpasswd=/tmp/htpasswd-users \
  -n openshift-config
```

Verify the secret exists:

```bash
oc get secret htpasswd-secret -n openshift-config
```

```
NAME              TYPE     DATA   AGE
htpasswd-secret   Opaque   1      5s
```

### Step 5: Configure the OAuth Server to Use HTPasswd

Apply the OAuth configuration manifest that references the HTPasswd secret:

```bash
oc apply -f manifests/oauth-htpasswd.yaml
```

The manifest (`manifests/oauth-htpasswd.yaml`) configures the OAuth server to use the HTPasswd identity provider:

```yaml
apiVersion: config.openshift.io/v1
kind: OAuth
metadata:
  name: cluster
spec:
  identityProviders:
    - name: htpasswd-local
      mappingMethod: claim
      type: HTPasswd
      htpasswd:
        fileData:
          name: htpasswd-secret
```

Key fields:
- **`name: htpasswd-local`** -- a label for this provider, shown on the login page
- **`mappingMethod: claim`** -- each identity maps to a unique user (first login claims the username)
- **`htpasswd.fileData.name`** -- references the Secret containing the htpasswd file

After applying, the OAuth operator will redeploy the OAuth server pods. This takes 1-2 minutes:

```bash
# Watch the OAuth pods restart
oc get pods -n openshift-authentication -w
```

Wait until the new pods show `Running` and `1/1` ready. Press `Ctrl+C` to stop watching.

### Step 6: Log In with the New HTPasswd Users

Test the new identity provider by logging in as each user:

```bash
# Log out first
oc logout

# Log in as the admin user we created
oc login -u admin -p redhat123 https://api.crc.testing:6443
```

```
Login successful.

You don't have any projects. You can try to create a new project, by running

    oc new-project <projectname>
```

```bash
# Verify your identity
oc whoami
```

```
admin
```

```bash
# Check your token
oc whoami -t
```

```
sha256~xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Note: This `admin` user has **no special privileges yet** -- it is just a regular authenticated user. The username "admin" does not grant any extra power. You must assign roles via RBAC (covered in L1-M2.3).

### Step 7: Examine OAuth Tokens and User Resources

Log back in as `kubeadmin` to inspect the authentication resources:

```bash
oc login -u kubeadmin -p <your-kubeadmin-password> https://api.crc.testing:6443

# List all users known to the cluster
oc get users
```

```
NAME        UID                                    FULL NAME   IDENTITIES
admin       xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx               htpasswd-local:admin
developer   xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx               htpasswd-local:developer
```

Users appear after their first login. Notice the `IDENTITIES` column links each user to the identity provider.

```bash
# List identities -- the mapping between IdP and users
oc get identities
```

```
NAME                      IDP NAME         IDP USER NAME   USER NAME   USER UID
htpasswd-local:admin      htpasswd-local   admin           admin       xxxxxxxx-...
htpasswd-local:developer  htpasswd-local   developer       developer   xxxxxxxx-...
```

```bash
# List active OAuth access tokens (there may be many)
oc get oauthaccesstokens | head -10
```

### Step 8: Understand Token Lifecycle

OAuth tokens in OpenShift have a configurable lifetime:

```bash
# View the OAuth server configuration for token timeouts
oc get oauth cluster -o jsonpath='{.spec.tokenConfig}' 2>/dev/null
echo
```

The default token lifetime is 24 hours. You can customize this in the OAuth resource:

```yaml
spec:
  tokenConfig:
    accessTokenMaxAgeSeconds: 28800  # 8 hours
```

Compare this with Kubernetes, where ServiceAccount tokens (bound tokens) have a configurable expiration via `TokenRequest` API, but client certificates do not expire until the CA certificate does (often 1 year or more by default).

### Step 9: View OAuth Configuration in the Web Console

Open the Web Console to see the authentication configuration visually:

1. Navigate to: https://console-openshift-console.apps-crc.testing
2. Log in with `admin` / `redhat123` -- notice the login page now shows "htpasswd-local" as a provider
3. After logging in, switch to the **Administrator** perspective (if you have access)
4. Go to **Administration > Cluster Settings > Configuration > OAuth**
5. You can see the identity providers listed and managed from here

## Verification

Run these commands to confirm everything is working:

```bash
# 1. Verify the OAuth resource has the HTPasswd provider
oc get oauth cluster -o jsonpath='{.spec.identityProviders[0].name}'
# Expected: htpasswd-local

# 2. Verify the secret exists
oc get secret htpasswd-secret -n openshift-config
# Expected: htpasswd-secret listed

# 3. Log in as each user and check identity
oc login -u admin -p redhat123 https://api.crc.testing:6443
oc whoami
# Expected: admin

oc login -u developer -p developer123 https://api.crc.testing:6443
oc whoami
# Expected: developer

oc login -u viewer -p viewer123 https://api.crc.testing:6443
oc whoami
# Expected: viewer

# 4. Verify users are created (log back in as kubeadmin)
oc login -u kubeadmin -p <your-kubeadmin-password> https://api.crc.testing:6443
oc get users
# Expected: admin, developer, viewer listed

# 5. Verify identities exist
oc get identities
# Expected: htpasswd-local:admin, htpasswd-local:developer, htpasswd-local:viewer
```

## K8s vs OpenShift Comparison

| Aspect | Kubernetes | OpenShift |
|--------|-----------|-----------|
| Authentication server | None built-in; must configure external OIDC, webhook, or certificates | Built-in OAuth 2.0 server, runs as a platform component |
| Login command | No `kubectl login`; manually configure kubeconfig | `oc login -u <user> -p <password> <server>` |
| Identity providers | Must set up externally (Dex, Keycloak, cloud IAM) | Pluggable via `OAuth` CR: HTPasswd, LDAP, GitHub, OIDC, etc. |
| User objects | No `User` resource; users exist only in external systems | `User` and `Identity` resources tracked in etcd |
| Credentials in kubeconfig | Client certificates, bearer tokens, or exec plugins | OAuth access tokens (time-limited, revocable) |
| Token lifetime | Client certs: long-lived; SA tokens: configurable | Default 24h, configurable via `tokenConfig` |
| Token revocation | Difficult -- requires CRL or short-lived tokens | `oc delete oauthaccesstoken <token>` or logout |
| Web Console login | Dashboard uses ServiceAccount token or proxy | Integrated OAuth login page with IdP selection |
| ServiceAccount tokens | Primary native auth mechanism | Also supported, plus human-user OAuth tokens |
| Multi-provider support | Requires OIDC proxy configuration | Native -- list multiple providers in the `OAuth` CR |

## Key Takeaways

- OpenShift includes a **built-in OAuth server** that eliminates the need to set up external authentication infrastructure for human users -- the single biggest developer-experience improvement over vanilla Kubernetes.
- **Identity providers are pluggable** via the `OAuth` custom resource (`oauth/cluster`). HTPasswd is simplest; production environments typically use LDAP, OIDC, or GitHub.
- `oc login` authenticates against the OAuth server and stores a **time-limited, revocable token** in your kubeconfig -- more secure than long-lived client certificates.
- OpenShift tracks **User** and **Identity** objects in the cluster, making it easy to audit who has authenticated and how.
- HTPasswd is great for local development (CRC) and labs, but you should use a centralized identity provider (LDAP, OIDC) for any production or team environment.

## Cleanup

```bash
# Log in as cluster admin
oc login -u kubeadmin -p <your-kubeadmin-password> https://api.crc.testing:6443

# Remove the HTPasswd identity provider (reset OAuth to empty)
oc apply -f manifests/oauth-reset.yaml

# Delete the htpasswd secret
oc delete secret htpasswd-secret -n openshift-config

# Delete user and identity objects created during login
oc delete user admin developer viewer
oc delete identity htpasswd-local:admin htpasswd-local:developer htpasswd-local:viewer

# Clean up the local htpasswd file
rm -f /tmp/htpasswd-users

# Wait for OAuth pods to stabilize
oc get pods -n openshift-authentication -w
# Press Ctrl+C once pods are Running
```

## Next Steps

In **L1-M2.3 -- RBAC Deep Dive**, you will learn how to assign roles and permissions to the users you just created. You will explore OpenShift's default roles (`admin`, `edit`, `view`, `cluster-admin`), create RoleBindings, and discover Security Context Constraints (SCCs) -- OpenShift's answer to Kubernetes Pod Security Policies.
