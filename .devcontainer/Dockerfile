FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl jq git ca-certificates openssl libffi-dev sqlite3 \
    zsh fonts-powerline unzip \
    && rm -rf /var/lib/apt/lists/*

# Node 20 via NodeSource
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /workspace

RUN groupadd -r vscode && useradd -r -g vscode -m -s /bin/bash vscode && \
    chown -R vscode:vscode /workspace

RUN su - vscode -c "curl -fsSL https://github.com/deluan/zsh-in-docker/releases/download/v1.2.1/zsh-in-docker.sh | sh -s -- -x -t robbyrussell -p https://github.com/zsh-users/zsh-autosuggestions -p https://github.com/zsh-users/zsh-syntax-highlighting"

RUN curl -s https://ohmyposh.dev/install.sh | bash -s -- -d /usr/local/bin && \
    su - vscode -c "mkdir -p /home/vscode/.poshthemes && \
    curl -fsSL https://raw.githubusercontent.com/JanDeDobbeleer/oh-my-posh/main/themes/kushal.omp.json -o /home/vscode/.poshthemes/kushal.omp.json && \
    chmod 644 /home/vscode/.poshthemes/kushal.omp.json"

RUN chsh -s /usr/bin/zsh vscode || usermod -s /usr/bin/zsh vscode

ENV SHELL=/usr/bin/zsh
ENV PYTHONPATH=/workspace/backend
ENV PYTHONUNBUFFERED=1
