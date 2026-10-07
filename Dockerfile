FROM python:3.10-slim

WORKDIR /app

COPY . /app

ENV PORT=8888
ENV VOIDCORE_ADMIN_PASS=voidcore_admin_2026

EXPOSE 8888

CMD ["python", "master_server.py"]
