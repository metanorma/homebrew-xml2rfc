FROM ubuntu:24.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
#ENV HOMEBREW_NO_ANALYTICS=1
#ENV HOMEBREW_INSTALL_DIR=/home/linuxbrew/.linuxbrew
#ENV PATH="$HOMEBREW_INSTALL_DIR/bin:$PATH"

RUN apt-get update && \
    apt-get install -y -q --allow-unauthenticated \
    git \
    sudo


RUN apt-get install -y -q build-essential procps curl file git

RUN useradd -ms /bin/bash brewuser
USER brewuser

RUN git clone https://github.com/Homebrew/brew ~/.linuxbrew/Homebrew \
&& mkdir ~/.linuxbrew/bin \
&& ln -s ../Homebrew/bin/brew ~/.linuxbrew/bin \
&& eval $(~/.linuxbrew/bin/brew shellenv) \
&& brew --version

RUN ~/.linuxbrew/bin/brew --version

COPY Formula Formula

RUN ~/.linuxbrew/bin/brew install --build-from-source --verbose --include-test --formula Formula/xml2rfc.rb
