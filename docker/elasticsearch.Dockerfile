FROM docker.elastic.co/elasticsearch/elasticsearch:8.13.0

# Chinese analysis is provided by the built-in smartcn plugin, which ships in
# the official image and needs no download. ``service_backends.py`` resolves
# the analyzer at runtime (smartcn -> standard) so no extra plugin install is
# required here. To use IK instead, add a RUN layer that installs
# analysis-ik matching the ES version.
RUN bin/elasticsearch-plugin install -b analysis-smartcn
