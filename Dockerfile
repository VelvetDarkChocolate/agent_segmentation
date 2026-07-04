FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY requirements-dev.txt /app/requirements-dev.txt
COPY causal_conv1d-1.0.0+cu118torch2.1cxx11abiFALSE-cp39-cp39-linux_x86_64.whl /app/
COPY mamba_ssm-1.0.1+cu118torch2.1cxx11abiFALSE-cp39-cp39-linux_x86_64.whl /app/

RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu118 \
        torch==2.1.0+cu118 torchvision==0.16.0+cu118

RUN pip install --no-cache-dir --no-deps \
        /app/causal_conv1d-1.0.0+cu118torch2.1cxx11abiFALSE-cp39-cp39-linux_x86_64.whl

RUN pip install --no-cache-dir \
        fastapi uvicorn python-multipart pillow "numpy<2" \
        ml-collections einops timm yacs pyyaml packaging ninja transformers==4.46.3

RUN pip install --no-cache-dir --no-deps \
        /app/mamba_ssm-1.0.1+cu118torch2.1cxx11abiFALSE-cp39-cp39-linux_x86_64.whl

COPY . /app

ENV APP_VERSION=0.1.0
ENV MODEL_PATH=""

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
