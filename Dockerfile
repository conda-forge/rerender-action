FROM mambaorg/micromamba:git-0f27156 AS build-env

ENV PYTHONDONTWRITEBYTECODE=1
USER root

# make sure the install below is not cached by docker
ADD https://loripsum.net/api /opt/docker/etc/gibberish-to-bust-docker-image-cache

COPY environment.yml /tmp/environment.yml

RUN echo "**** install base env ****" && \
    micromamba install --yes --quiet --name base -c conda-forge git conda python=3.11 && \
    source /opt/conda/etc/profile.d/conda.sh && \
    conda activate base && \
    micromamba install --yes --quiet --name base --file /tmp/environment.yml && \
    touch ${CONDA_PREFIX}/conda-meta/pinned && \
    echo "conda-forge-tick =="$(conda list conda-forge-tick | grep conda-forge-tick | awk '{print $2}') \
      >> ${CONDA_PREFIX}/conda-meta/pinned && \
    cat ${CONDA_PREFIX}/conda-meta/pinned

RUN echo "**** cleanup ****" && \
    micromamba clean --all --force-pkgs-dirs --yes && \
    find "${MAMBA_ROOT_PREFIX}" -follow -type f \( -iname '*.a' -o -iname '*.pyc' -o -iname '*.js.map' \) -delete
RUN echo "**** finalize ****" && \
    mkdir -p "${MAMBA_ROOT_PREFIX}/locks" && \
    chmod 777 "${MAMBA_ROOT_PREFIX}/locks"

FROM frolvlad/alpine-glibc:alpine-3.16_glibc-2.34

COPY --from=build-env /opt/conda /opt/conda

COPY BASE_IMAGE_LICENSE /

LABEL maintainer="conda-forge (@conda-forge/core)"

ENV LANG en_US.UTF-8

ARG CONDA_DIR="/opt/conda"

ENV PATH="$CONDA_DIR/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1

COPY entrypoint /opt/docker/bin/entrypoint
RUN mkdir -p webservices_dispatch_action
COPY / webservices_dispatch_action/
RUN source /opt/conda/etc/profile.d/conda.sh && \
    cd webservices_dispatch_action && \
    conda activate base && \
    pip install --no-build-isolation -e .

ENTRYPOINT ["/opt/conda/bin/tini", "--", "/opt/docker/bin/entrypoint"]
