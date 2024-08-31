# webservices-dispatch-action

a docker image to run conda-forge's admin webservices GitHub Actions integrations

## Description

This image contains the code and integrations to run conda-forge's webservices GitHub Actions
integrations. Those integrations perform basic tasks like rerendering feedstocks and updating
to new versions.

## License

This image is licensed under [BSD-3 Clause](https://github.com/conda-forge/webservices-dispatch-action/blob/main/LICENSE).

## Documentation & Contributing

You can find documentation for how to use the image on the
upstream [repo](https://github.com/conda-forge/webservices-dispatch-action) and in the sections below.

To get in touch with the maintainers of this image, please [make an issue](https://github.com/conda-forge/webservices-dispatch-action/issues/new/choose)
and bump the `@conda-forge/core` team.

Contributions are welcome in accordance
with conda-forge's [code of conduct](https://conda-forge.org/community/code-of-conduct/). We accept them through pull requests on the
upstream [repo](https://github.com/conda-forge/webservices-dispatch-action/compare).

## Important Image Tags

- prod: the current production image in use for feedstocks
- dev: a tag that is overwritten and used for CI testing

## Getting Started & Usage

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

Then issue a repository dispatch event in the GitHub API with the correct JSON blob.

For example, a rerender uses:

```json
{"event_type": "rerender", "client_payload": {"pr": 12}}
```

The form of the JSON blobs for various actions can be found in
the [package entrypoint](https://github.com/conda-forge/webservices-dispatch-action/blob/main/webservices_dispatch_action/__main__.py).
