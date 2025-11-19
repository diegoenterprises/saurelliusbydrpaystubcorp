# Lambda container image for Saurellius Playwright generator
FROM public.ecr.aws/lambda/python:3.11

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install -r requirements.txt && \
    python -m playwright install chromium

COPY . ${LAMBDA_TASK_ROOT}

CMD [ "lambda.lambda_handler" ]
