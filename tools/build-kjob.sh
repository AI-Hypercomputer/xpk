#! /bin/bash

set -e

docker build -f tools/Dockerfile-kjob -t xpk_kjob tools/
docker run -idt --name xpk_kjob_container xpk_kjob
docker cp xpk_kjob_container:/kjob/bin/kubectl-kjob kubectl-kjob
docker rm -f xpk_kjob_container
docker image rm xpk_kjob
