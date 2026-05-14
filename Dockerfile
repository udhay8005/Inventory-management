# Odoo CE 19 + lightweight Python deps for offline AI inside the same container.
# Keeps deployment minimal: one Odoo container, one DB. AI worker is optional.
FROM odoo:19.0

USER root

# Fonts only — psycopg2 is bundled with the Odoo image, and the Python
# libs below all ship manylinux wheels so we don't need build toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Lightweight forecasting stack (~80MB).
# statsmodels gives us Holt-Winters / SES with no GPU and ~30MB resident.
COPY ./requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# pip installing tzdata/pandas alongside the apt-installed pytz leaves
# pkg_resources unable to read pytz's bundled zoneinfo (loader has no
# get_data()), which breaks the Odoo activity widget. Force a clean pytz.
RUN pip3 install --no-cache-dir --force-reinstall --no-deps --break-system-packages pytz

# Pre-create log dir owned by odoo user
RUN mkdir -p /var/log/odoo && chown odoo:odoo /var/log/odoo

USER odoo
