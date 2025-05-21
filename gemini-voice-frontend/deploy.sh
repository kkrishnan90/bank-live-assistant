#!/bin/bash

# Deploy Frontend to Cloud Run Script
# This script will build and deploy the frontend to Cloud Run

# Set variables
PROJECT_ID="account-pocs"
COMMIT_SHA=$(date +%Y%m%d-%H%M%S)
SERVICE_NAME="frontend-service"
REGION="us-central1"

# Use the backend URL provided
BACKEND_URL="https://gemini-backend-service-1018963165306.us-central1.run.app"

echo "=== Deploying Frontend to Cloud Run ==="
echo "Project ID: $PROJECT_ID"
echo "Commit SHA: $COMMIT_SHA"
echo "Service Name: $SERVICE_NAME"
echo "Region: $REGION"
echo "Backend URL: $BACKEND_URL"

# Navigate to the frontend directory (in case script is run from elsewhere)
cd "$(dirname "$0")"

# Create .env file with the backend URL
echo "REACT_APP_BACKEND_URL=$BACKEND_URL" > .env
echo "Created .env file with BACKEND_URL: $BACKEND_URL"

# Update the proxy in package.json to point to the Cloud Run backend
sed -i '' "s|\"proxy\": \"http://localhost:8000\"|\"proxy\": \"$BACKEND_URL\"|" package.json
echo "Updated proxy in package.json to: $BACKEND_URL"

# Deploy with Cloud Build
echo "=== Deploying frontend with Cloud Build ==="
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_PROJECT_ID=$PROJECT_ID,_COMMIT_SHA=$COMMIT_SHA,_BACKEND_URL=$BACKEND_URL \
  .

if [ $? -eq 0 ]; then
  echo "=== Getting service URL ==="
  SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region=$REGION --format 'value(status.url)')
  echo "=== Frontend is available at: $SERVICE_URL ==="
  # Save the URL to a file for future reference
  echo $SERVICE_URL > ../frontend_url.txt
  echo "=== URL saved to ../frontend_url.txt ==="
else
  echo "=== Frontend deployment failed! ==="
  exit 1
fi
