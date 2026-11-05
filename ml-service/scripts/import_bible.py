cd ~/src/BibleAnswers/ml-service
.venv/bin/pip install "psycopg[binary]" python-dotenv
.venv/bin/pip freeze > requirements.txt
echo 'DATABASE_URL=postgresql://bibleanswers:bibleanswers@localhost:5433/bibleanswers' >> .env
