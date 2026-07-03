
# Tutorial

What I would like to see in the tutorial to better understand the OpenShift.

## Basics

1) how to run database (Parquet files) + API (Python with DuckDB) + UI (React)

2) how to expose the UI and API outside
- via Route object?
- via Service Mesh - istio?
- is it replacement for a Traefik that I am currently using in vanilla k8s?

3) how to run multiple microservices in openshift

4) example of using `Build & Image Resources`
- `build.openshift.io/v1 BuildConfig`
- ... etc.

5) example of using `Authentication & Authorization Resources`
- `config.openshift.io/v1 OAuth`
- ...etc.
- Is it replacement for a Keycloak that I am currently using in vanilla k8s?

6) how to create a "Project" object and what is the reason to have it?
- `project.openshift.io/v1 Project`


7) How to do `monitoring` and `logging`
- via some custom API/service (python)

8) Example of using CI/CD
- for building my own source code on github ??
- pushing the docker container to registry (github one) ??
- deploying to cluster ??

9) Example of GitOps
- so I understand how it works, and why I should use it

10) Example of serverless
- Why should I use it?
- I never fully understood the reason why to use serverless

