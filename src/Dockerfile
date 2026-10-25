FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py emails.json ./
# Khi Quang làm xong thư mục templates/, dòng dưới sẽ copy luôn giao diện vào
COPY templates/ ./templates/

EXPOSE 5000

CMD ["python", "app.py"]