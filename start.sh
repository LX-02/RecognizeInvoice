#!/bin/bash
source /root/anaconda3/etc/profile.d/conda.sh

# 修改 conda 环境
conda activate waste_water

cd /data/RecognizeInvoice

PORT=8080
PID=$(lsof -t -i:$PORT)

if [ -n "$PID" ]; then
  echo "Port $PORT is already in use."
  kill -9 $PID
  echo "Process $PID killed."
else
  echo "Port $PORT is available."
fi

uvicorn app.main:app --host 0.0.0.0 --port $PORT --reload
