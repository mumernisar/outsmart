#!/bin/bash
# Setup script for Outsmart development environment

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Install SDK in editable mode
echo "Installing glueco-sdk..."
.venv/bin/pip install -e ../python-packages/glueco-sdk

# Install requirements
echo "Installing requirements..."
.venv/bin/pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run the app:"
echo "  cd forks/outsmart"
echo "  .venv/bin/python -m streamlit run app.py"
echo ""
echo "Or activate the venv first:"
echo "  source .venv/bin/activate"
echo "  streamlit run app.py"
