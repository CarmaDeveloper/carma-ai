# CARMA AI RAG Application

A FastAPI-based RAG (Retrieval-Augmented Generation) application for intelligent document processing and report generation using AWS services and vector search capabilities.

## Features

- **FastAPI Framework**: Modern, high-performance web framework with async support
- **Document Ingestion**: Comprehensive S3-based document processing pipeline
- **RAG Implementation**: Context-aware report generation using vector search
- **AWS Integration**: Bedrock for LLMs/embeddings, Comprehend for PII detection, S3 for storage
- **Vector Search**: PostgreSQL with pgvector for similarity search
- **PII Protection**: Automatic detection and redaction of sensitive information
- **Multi-format Support**: PDF, Word, Text, Markdown, HTML, and CSV files
- **Record Management**: Track document chunks and relationships
- **Background Processing**: Async document ingestion with status tracking
- **Production Ready**: Structured logging, type safety, and comprehensive error handling

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │────│   Service Layer │────│   AWS Services  │
│                 │    │                 │    │                 │
│ • API Routes    │    │ • Report Gen    │    │ • Bedrock LLM   │
│ • Validation    │    │ • Ingestion     │    │ • Comprehend    │
│ • Error Handle  │    │ • Vector Store  │    │ • S3 Storage    │
│ • Background    │    │ • PII Detection │    │ • Embeddings    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                │
                                │                         
                       ┌─────────────────┐
                       │  PostgreSQL +   │
                       │    pgvector     │
                       └─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- AWS credentials configured
- Required AWS services enabled:
  - AWS Bedrock (for LLM and embeddings)
  - AWS Comprehend (for PII detection)
  - AWS S3 (for document storage)

### Installation

1. **Clone and navigate:**
```bash
git clone <repository-url>
cd carma-ai
```

2. **Start PostgreSQL with pgvector:**
```bash
cd deployment
docker-compose up -d pgvector
```

3. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

4. **Install dependencies:**
```bash
pip install -r requirements.txt
```

5. **Configure environment variables:**
```bash
# Copy and edit environment variables
cp .env.example .env
# Edit .env with your configuration (see Configuration section)
```

6. **Run the application:**
```bash
# Using the run script
python run.py
```

The API will be available at `http://localhost:8000`

### API Documentation

- **Interactive API Docs**: `http://localhost:8000/docs`
- **Alternative Docs**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `POSTGRES_HOST` | PostgreSQL host | `localhost` | Yes |
| `POSTGRES_PORT` | PostgreSQL port | `5432` | Yes |
| `POSTGRES_USER` | PostgreSQL username | `postgres` | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | `postgres` | Yes |
| `POSTGRES_DB` | PostgreSQL database name | `carma_ai` | Yes |
| `BEDROCK_REGION` | AWS Bedrock region | `ca-central-1` | No |
| `BEDROCK_EMBEDDING` | Bedrock embedding model | `amazon.titan-embed-text-v2:0` | Yes |
| `BEDROCK_MODEL` | Bedrock LLM model | `anthropic.claude-3-sonnet-20240229-v1:0` | Yes |
| `S3_BUCKET_NAME` | S3 bucket for documents | `carma-rag-bucket` | Yes |
| `S3_REGION` | S3 region | `ca-central-1` | No |
| `COMPREHEND_REGION` | AWS Comprehend region | `ca-central-1` | No |
| `COMPREHEND_THRESHOLD` | PII detection threshold | `0.9` | No |
| `COMPREHEND_TYPES` | PII types to detect | `["LOCATION", "PERSON"]` | No |
| `CHUNK_SIZE` | Text chunk size for splitting | `1000` | No |
| `CHUNK_OVERLAP` | Text chunk overlap | `200` | No |
| `MAX_FILE_SIZE` | Maximum file size (bytes) | `52428800` (50MB) | No |
| `DEBUG` | Enable debug mode | `True` | No |
| `LOG_LEVEL` | Logging level | `DEBUG` | No |


## API Usage

### Document Ingestion

Upload documents to S3 first, then ingest them into knowledge bases:

```bash
# Ingest a document from S3
curl -X POST "http://localhost:8000/v1/ingestion/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_id": "a71860c9-b8df-47c5-a11f-3e1ac6086026",
    "filename": "document.pdf"
  }'

# Start async ingestion (returns immediately)
curl -X POST "http://localhost:8000/v1/ingestion/ingest-async" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_id": "kb-123",
    "filename": "large-document.pdf"
  }'

# Check ingestion status
curl "http://localhost:8000/v1/ingestion/status/kb-123"

# Get supported file formats
curl "http://localhost:8000/v1/ingestion/supported-formats"

# Remove a document
curl -X DELETE "http://localhost:8000/v1/ingestion/remove" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_id": "kb-123",
    "filename": "document.pdf"
  }'
```

**S3 Document Structure:**
Documents should be stored in S3 with the following structure:
```
s3://your-bucket/
├── knowledge-id-1/
│   ├── document1.pdf
│   └── document2.docx
└── knowledge-id-2/
    ├── report1.txt
    └── data.csv
```

### Report Generation

Generate reports using RAG with Q&A pairs:

```bash
curl -X POST "http://localhost:8000/v1/reports/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_id": "kb-123",
    "prompt": [
      ["system", "You are a helpful assistant that generates comprehensive reports."],
      ["human", "Generate a detailed report based on the provided Q&A pairs and context."]
    ],
    "qas": [
      {
        "question": "What are the main findings?",
        "answer": "The analysis shows significant improvements in efficiency and cost reduction."
      },
      {
        "question": "What are the recommendations?",
        "answer": "We recommend implementing the proposed changes in Q1 2024."
      }
    ]
  }'
```

### Response Format

```json
{
  "message": "Based on the provided information and relevant documentation, here is the comprehensive report...",
  "references": ["document1.pdf", "technical-spec.docx"],
  "knowledge_id": "kb-123"
}
```

## Supported File Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| PDF | `.pdf` | Portable Document Format |
| Word | `.docx`, `.doc` | Microsoft Word documents |
| Text | `.txt` | Plain text files |
| Markdown | `.md`, `.markdown` | Markdown files |
| HTML | `.html`, `.htm` | Web pages |
| CSV | `.csv` | Comma-separated values |
