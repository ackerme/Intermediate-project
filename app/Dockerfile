# גירסת פייטון
FROM python:3.12-slim

# תיקיית עבודה בתוך הקונטיינר
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5000

CMD ["python", "app.py"]                         

# גירסת פייטון
# תקיית עבודה בתוך הקונטינר
# עתקת קובץ לתקיית עבודה
# התקנה של מה שצריך 
# עתקת קובץ הקו לתקיית עבודה
# חסיפת פוט 5000
# יריץ את האפליקציה כאשר הקונטינר מופעל