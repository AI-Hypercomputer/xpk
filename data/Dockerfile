# """
# Copyright 2024 Google LLC

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#      https://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# """

# THIS IS AN DEVELOPER DOCKER IMAGE THAT SHOULD NOT BE USED AT PRODUCTION ENV

# Use a google-cloud-cli image as the base
FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:stable

# Install necessary tools and libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        git \
        make \
        unzip \
        wget

# Install Terraform
RUN wget -q "https://releases.hashicorp.com/terraform/1.5.2/terraform_1.5.2_linux_amd64.zip" -O terraform.zip && \
    unzip terraform.zip && \
    mv terraform /usr/local/bin/ && \
    rm terraform.zip

# Install Packer
RUN wget -q "https://releases.hashicorp.com/packer/1.8.6/packer_1.8.6_linux_amd64.zip" -O packer.zip && \
    unzip packer.zip && \
    mv packer /usr/local/bin/ && \
    rm packer.zip

# Install Go
ENV GO_VERSION 1.23.3

RUN wget -q "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" -O go.tar.gz && \
    tar -C /usr/local -xzf go.tar.gz && \
    rm go.tar.gz

# Set GOPATH and add to PATH
ENV GOPATH /go
ENV PATH $PATH:/usr/local/go/bin:$GOPATH/bin

# Clone the Cluster Toolkit repository
RUN git clone https://github.com/GoogleCloudPlatform/cluster-toolkit.git /cluster-toolkit

# Build the Cluster Toolkit
WORKDIR /cluster-toolkit
RUN apt-get install -y python3-pip
RUN make

# Make gcluster available
RUN mv gcluster /usr/local/bin/gcluster 

# Command to execute when running the container (placeholder)
CMD ["/bin/bash"]

