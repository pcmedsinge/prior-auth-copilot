FROM eclipse-temurin:17-jre-alpine

# Synthea rolling release JAR published by MITRE/HL7.
# To pin to a specific tagged release replace the URL with:
#   https://github.com/synthetichealth/synthea/releases/download/vX.Y.Z/synthea-with-dependencies.jar
ARG SYNTHEA_JAR_URL=https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar

RUN apk add --no-cache curl \
    && mkdir -p /synthea \
    && curl -fSL "${SYNTHEA_JAR_URL}" -o /synthea/synthea.jar \
    && apk del curl

WORKDIR /synthea

# Volume conventions (set by docker-compose / loader script):
#   /output   — FHIR bundle output written here (host-mounted, gitignored)
#   /modules  — custom GMF modules directory (data/synthea-config/modules/)
#   /synthea/synthea.properties — Synthea config (data/synthea-config/synthea.properties)

ENTRYPOINT ["java", "-jar", "/synthea/synthea.jar"]

# Default: 10 patients, US, custom modules dir mounted at /modules.
# Overridden by docker compose run / load_synthea.py generate.
CMD ["-p", "10", "-d", "/modules"]
