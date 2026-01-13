FROM ckan/ckan-base:2.10.1
#FROM ckan/ckan-base:2.9.9

ARG BRANCH_NAME
ARG COMMIT_SHA

LABEL branch="$BRANCH_NAME"
LABEL commit_sha="$COMMIT_SHA"


# Set up environment variables
ENV APP_DIR=/srv/app
ENV TZ=UTC
RUN echo ${TZ} > /etc/timezone

# Make sure both files are not exactly the same
RUN if ! [ /usr/share/zoneinfo/${TZ} -ef /etc/localtime ]; then \
  cp /usr/share/zoneinfo/${TZ} /etc/localtime ;\
  fi ;

# Install any extensions needed by your CKAN instance
# - Make sure to add the plugins to CKAN__PLUGINS in the .env file
# - Also make sure all extra configuration options are added to the CKAN config file (ckan.ini)
#   This can be done by creating an overriding start_ckan_dev_development.sh file:
#   (https://github.com/ckan/ckan-docker-base/blob/main/ckan-2.9/dev/setup/start_ckan_development.sh) ie: updating the 'ckan config-tool' lines
#   For more on config-tool please see https://docs.ckan.org/en/latest/maintaining/cli.html#config-tool-tool-for-editing-options-in-a-ckan-config-file
#   or using Crudini (https://github.com/pixelb/crudini)
#
# For instance:
#
### XLoader ###
#RUN pip3 install -e 'git+https://github.com/ckan/ckanext-xloader.git@master#egg=ckanext-xloader' && \
#    pip3 install -r ${APP_DIR}/src/ckanext-xloader/requirements.txt && \
#    pip3 install -U requests[security]

### Harvester ###
#RUN pip3 install -e 'git+https://github.com/ckan/ckanext-harvest.git@master#egg=ckanext-harvest' && \
#    pip3 install -r ${APP_DIR}/src/ckanext-harvest/pip-requirements.txt
# will also require gather_consumer and fetch_consumer processes running (please see https://github.com/ckan/ckanext-harvest)



### Pages ###
#RUN  pip3 install -e git+https://github.com/ckan/ckanext-pages.git#egg=ckanext-pages

### Spatial extension ###
RUN apk add python3-dev libxml2-dev libxslt-dev geos geos-dev proj proj-dev proj-util py3-shapely
RUN pip install --upgrade pip

RUN pip install future

RUN pip install -e "git+https://github.com/ckan/ckanext-spatial.git#egg=ckanext-spatial"
COPY spatial-reqs.txt /tmp/spatial-reqs.txt
RUN pip install -r /tmp/spatial-reqs.txt

RUN pip install future

### DOI extension ###
RUN pip install -e "git+https://github.com/AuScope/ckanext-doi.git@auscope_pidinst#egg=ckanext-doi"

### ISO19115 extension ###
RUN pip install -e "git+https://github.com/AuScope/ckanext-iso19115.git@auscope_data_repo_customise#egg=ckanext-iso19115"

### Contact extension ###
RUN pip install ckanext-contact

### S3 Filestore extension ###
RUN pip install -e "git+https://github.com/keitaroinc/ckanext-s3filestore.git#egg=ckanext-s3filestore"

### Scheming ###
RUN pip install -e "git+https://github.com/ckan/ckanext-scheming.git@master#egg=ckanext-scheming"

### Repeating fields ###
RUN pip install -e "git+https://github.com/open-data/ckanext-repeating.git#egg=ckanext-repeating"

### Composite fields ###
RUN pip install -e "git+https://github.com/EnviDat/ckanext-composite.git#egg=ckanext-composite"

### Zip preview ###
RUN pip install -e "git+https://github.com/AuScope/ckanext-zippreview.git@master#egg=ckanext-zippreview"

# ### DCAT plugins ###
RUN pip install -r "https://raw.githubusercontent.com/ckan/ckanext-dcat/master/requirements.txt"
RUN pip install -e "git+https://github.com/AuScope/ckanext-dcat.git@auscope_customise#egg=ckanext-dcat"

# Clone the extension(s) your are writing for your own project in the `src` folder
# to get them mounted in this image at runtime

COPY setup/prerun.py.override ${APP_DIR}/prerun.py
COPY setup/start_ckan.sh.override ${APP_DIR}/start_ckan.sh
COPY setup/create_auscope_org.sql ${APP_DIR}/create_auscope_org.sql
# Apply any patches needed to CKAN core or any of the built extensions (not the
# runtime mounted ones)

COPY patches ${APP_DIR}/patches

RUN for d in $APP_DIR/patches/*; do \
  if [ -d $d ]; then \
  for f in `ls $d/*.patch | sort -g`; do \
  cd $SRC_DIR/`basename "$d"` && echo "$0: Applying patch $f to $SRC_DIR/`basename $d`"; patch -p1 < "$f" ; \
  done ; \
  fi ; \
  done


# I am getting oidc_pkce error in dev env. Hence, added below.
COPY src ${APP_DIR}/src_extensions
COPY src/shared/public /shared/public
COPY src/shared/templates /shared/templates

# RUN pip install $APP_DIR/src_extensions/ckanext-oidc-pkce

RUN pip install $APP_DIR/src_extensions/ckanext-oidc-pkce && \
  pip install $APP_DIR/src_extensions/ckanext-pidinst-theme && \
  pip install pandas openpyxl requests python-multipart

RUN chmod +x ${APP_DIR}/start_ckan.sh
# RUN chmod +x ${APP_DIR}/start_ckan_development.sh





#================================================================
# OLD PROD - VERSION
#================================================================

# # Set up environment variables
# ENV APP_DIR=/srv/app
# ENV TZ=UTC
# RUN echo ${TZ} > /etc/timezone

# # Make sure both files are not exactly the same
# RUN if ! [ /usr/share/zoneinfo/${TZ} -ef /etc/localtime ]; then \
#   cp /usr/share/zoneinfo/${TZ} /etc/localtime ;\
#   fi ;

# ### Spatial extension ###
# RUN apk add python3-dev libxml2-dev libxslt-dev geos geos-dev proj proj-dev proj-util py3-shapely
# RUN pip install --upgrade pip
# RUN pip install -e "git+https://github.com/ckan/ckanext-spatial.git#egg=ckanext-spatial"
# COPY spatial-reqs.txt /tmp/spatial-reqs.txt
# RUN pip install -r /tmp/spatial-reqs.txt

# ### DOI extension ###
# RUN pip install ckanext-doi
# COPY setup/start_ckan.sh.override ${APP_DIR}/start_ckan.sh
# COPY setup/prerun.py.override ${APP_DIR}/prerun.py

# ### Contact extension ###
# RUN pip install -e "git+https://github.com/AuScope/ckanext-contact.git#egg=ckanext-contact"

# ### S3 Filestore extension ###
# RUN pip install -e "git+https://github.com/keitaroinc/ckanext-s3filestore.git#egg=ckanext-s3filestore"

# ### Scheming Extension
# RUN pip install -e "git+https://github.com/ckan/ckanext-scheming.git#egg=ckanext-scheming"

# ### Repeating fields ###
# RUN pip install -e "git+https://github.com/open-data/ckanext-repeating.git#egg=ckanext-repeating"

# ### Composite fields ###
# RUN pip install -e "git+https://github.com/EnviDat/ckanext-composite.git#egg=ckanext-composite"

# ### Zip preview ###
# RUN pip install -e "git+https://github.com/datagovau/ckanext-zippreview.git#egg=ckanext-zippreview"


# # For production copy the source files into the image (Dev will mount them as a volume)
# COPY src ${APP_DIR}/src_extensions
# COPY src/shared /shared

# # Adding below paths similar to above.
# COPY src/shared/public /shared/public
# COPY src/shared/templates /shared/templates

# # # Install the extension(s) you wrote for your own project
# RUN pip install $APP_DIR/src_extensions/ckanext-oidc-pkce && \
#   pip install -e $APP_DIR/src_extensions/ckanext-auscope-theme && \
#   pip install -e $APP_DIR/src_extensions/ckanext-igsn-theme

# RUN chmod +x ${APP_DIR}/start_ckan.sh
