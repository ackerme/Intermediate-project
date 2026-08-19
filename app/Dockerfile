FROM python:3.12-slim                                 # גירסת פייטון

WORKDIR /app                                          # תקיית עבודה בתוך הקונטינר

COPY requirements.txt .                               # עתקת קובץ לתקיית עבודה
RUN pip install --no-cache-dir -r requirements.txt    # התקנה של מה שצריך

COPY app.py .                                         # עתקת קובץ הקו לתקיית עבודה

EXPOSE 5000                                           # חסיפת פוט 5000

CMD ["python", "app.py"]                              # יריץ את האפליקציה כאשר הקונטינר מופעל
