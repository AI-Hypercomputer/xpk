#!/bin/bash

readonly PLUGIN="gke-gcloud-auth-plugin"

# Officially supported installation methods
readonly GCLOUD_INSTALLER="gcloud"
readonly APT_INSTALLER="apt"
readonly YUM_INSTALLER="yum"

IS_GCLOUD_INSTALLER=false
INSTALL_CMD=""

function set_install_command() {
    OS=$(uname -s)
    case "$OS" in
    "Linux")
        if command -v ${APT_INSTALLER} &> /dev/null
        then
            INSTALL_CMD="apt-get install -y google-cloud-sdk-gke-gcloud-auth-plugin"
        elif command -v ${YUM_INSTALLER} &> /dev/null
        then
            INSTALL_CMD="yum install -y google-cloud-sdk-gke-gcloud-auth-plugin"
        else
            echo "Neither apt nor yum is available, using gcloud to install."
            IS_GCLOUD_INSTALLER=true
            INSTALL_CMD="gcloud components install gke-gcloud-auth-plugin --quiet"
        fi
        ;;
    "Darwin")
        IS_GCLOUD_INSTALLER=true
        INSTALL_CMD="gcloud components install gke-gcloud-auth-plugin --quiet"
        ;;
    *)
        echo "Unsupported OS: $OS"
        exit 1
        ;;
    esac
}

function install_plugin() {
  if [ "${IS_GCLOUD_INSTALLER}" = true ] && ! command -v ${GCLOUD_INSTALLER} &> /dev/null
  then
    echo "gcloud command could not be found, please install Google Cloud SDK first."
    exit 1
  fi

  echo "Installing ${PLUGIN}..."
  eval $INSTALL_CMD
}

function verify_plugin_installation() {
    if ${PLUGIN} --version &> /dev/null
    then
        echo "${PLUGIN} installation successful. Version info:"
        ${PLUGIN} --version
    else
        echo "${PLUGIN} installation failed or the plugin is not accessible in PATH."
        exit 1
    fi
}

set_install_command
install_plugin
verify_plugin_installation
