
FROM apache/airflow:3.3.2

ARG AIRFLOW_VERSION=3.3.2

COPY --chown=airflow:root airflow/requirements.txt /requirements.txt

RUN PYTHON_VERSION="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" \
    && pip install --no-cache-dir \
        "apache-airflow==${AIRFLOW_VERSION}" \
        -r /requirements.txt \
        --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

COPY --chown=airflow:root scripts/ /opt/pricepulse/scripts/
COPY --chown=airflow:root tests/ /opt/pricepulse/tests/

USER root

RUN mkdir -p /opt/pricepulse/data/raw /opt/pricepulse/data/processed \
    && chown -R airflow:root /opt/pricepulse

USER airflow
