# webservices-dispatch-action
[![tests](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/tests.yml/badge.svg)](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/tests.yml) [![pre-commit.ci status](https://results.pre-commit.ci/badge/github/conda-forge/webservices-dispatch-action/main.svg)](https://results.pre-commit.ci/latest/github/conda-forge/webservices-dispatch-action/main)

a GitHub action to run webservices tasks conda-forge feedstocks

## Usage

To use this action, add the following YAML file at `.github/workflows/webservices.yml`

```yaml
on: repository_dispatch

jobs:
  webservices:
    runs-on: ubuntu-latest
    name: webservices
    steps:
      - name: webservices
        id: webservices
        uses: conda-forge/webservices-dispatch-action@main
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          rerendering_github_token: ${{ secrets.RERENDERING_GITHUB_TOKEN }}
```

The admin web service will create the appropriate `dispatch` event with the
correct data.

For example, a rerender uses:

```json
{"event_type": "rerender", "client_payload": {"pr": 12}}
```

## Deployment

The GitHub action always points to the `prod` tag of the
[condaforge/webservices-dispatch-action](https://hub.docker.com/repository/docker/condaforge/webservices-dispatch-action)
Docker image.

 - To redeploy the rerender action, push a new image to the `prod` tag.

   ```bash
   docker build -t condaforge/webservices-dispatch-action:prod .
   docker push condaforge/webservices-dispatch-action:prod
   ```

 - To take the rerender action down, delete the tag from the Docker repository.
   The GitHub Action will still run in this case, but it will always fail.

 - **The docker image is rebuilt on a weekly basis with the docker-push.yml GHA. You must disable this
   workflow to prevent the prod tag from being repushed.**
