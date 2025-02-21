FROM python:3.9
RUN ln -snf /usr/share/zoneinfo/Asia/Seoul /etc/localtime
RUN mkdir /usr/src/app
WORKDIR /usr/src/app
COPY . .
RUN pip install --upgrade pip
RUN pip3 install -r requirements.txt
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get clean \
    && rm -rf /var/lib/apt/lists/*
CMD ["python3", "-m", "gunicorn", "--bind", ":8000", "--workers", "2", "jibsinpj.wsgi:application"]
