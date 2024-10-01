# MOVED TO [conda-forge-webservices](https://github.com/conda-forge/conda-forge-webservices)

This image build and GitHub Actions integration has been moved to [conda-forge-webservices](https://github.com/conda-forge/conda-forge-webservices). Please direct any PRs and issues there! :)

# webservices-dispatch-action
[![tests](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/tests.yml/badge.svg?event=merge_group)](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/tests.yml) [![pre-commit.ci status](https://results.pre-commit.ci/badge/github/conda-forge/webservices-dispatch-action/main.svg)](https://results.pre-commit.ci/latest/github/conda-forge/webservices-dispatch-action/main) [![container](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/container.yml/badge.svg)](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/container.yml) [![relock](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/relock.yml/badge.svg)](https://github.com/conda-forge/webservices-dispatch-action/actions/workflows/relock.yml)

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
