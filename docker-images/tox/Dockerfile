FROM gitlab-registry.cern.ch/linuxsupport/alma8-base
RUN \
    dnf install -y -q python3.11 python3-pip python39 python3.11-pip git ;\
    python3.11 -m pip install -U pip tox ;\
    python3.9 -m pip install -U pip tox ;\
    python3.6 -m pip install -U pip tox
