FROM python:3.10

WORKDIR /app

COPY . .

RUN pip install flask flask-login gunicorn flask-socketio qrcode pillow

EXPOSE 8000

CMD ["gunicorn","--bind","0.0.0.0:8000","app:app"]
