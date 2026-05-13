# Odoo CE 19 + lightweight Python deps for offline AI inside the same container.
# Keeps deployment minimal: one Odoo container, one DB. AI worker is optional.
FROM odoo:19.0

USER root

# System deps:
# - libpq-dev: psycopg
# - fonts-dejavu-core: barcode label rendering
# - python3-numpy / pandas via pip: ndarrays for forecasting
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        libpq-dev \
        build-essential \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Lightweight forecasting stack (~80MB).
# statsmodels gives us Holt-Winters / SES with no GPU and ~30MB resident.
COPY ./requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Pre-create log dir owned by odoo user
RUN mkdir -p /var/log/odoo && chown odoo:odoo /var/log/odoo

USER odoo
