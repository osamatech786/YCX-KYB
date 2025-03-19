# KYB Due Diligence System

## System Prompt

```
You are a seasoned business analyst with expertise in Know Your Business (KYB) due diligence. When given the name and website of a company, gather and summarize essential details including registration number, date of incorporation, beneficial owners, financial highlights, and any public risk indicators. Format your output in a structured JSON with keys: company_name, registration_number, incorporation_date, beneficial_owners, financial_summary, and risk_indicators.
```

## Overview

This system is designed to perform Know Your Business (KYB) due diligence on companies by gathering and summarizing essential business information. The AI assistant acts as a business analyst who can extract and organize key company details into a structured format.

## Input Format

The system expects inputs containing:
- Company name
- Company website

Example input:
```
Company: Acme Corporation
Website: https://www.acmecorp.com
```

## Output Format

The system returns a structured JSON with the following fields:

```json
{
  "company_name": "String - Full legal name of the company",
  "registration_number": "String - Official registration/incorporation number",
  "incorporation_date": "String - Date when the company was incorporated",
  "beneficial_owners": [
    {
      "name": "String - Name of beneficial owner",
      "ownership_percentage": "String - Percentage of ownership"
    }
  ],
  "financial_summary": {
    "revenue": "String - Latest annual revenue figure",
    "profit": "String - Latest profit/loss figure",
    "assets": "String - Total assets value",
    "liabilities": "String - Total liabilities"
  },
  "risk_indicators": [
    "String - Any public risk factors or red flags"
  ]
}
```

## Explanation of the Python Script

### Initialization:
- The script first retrieves the Groq API key from an environment variable and instantiates the Groq client.
- (Refer to Groq's documentation for setting up your API key.)

### Advanced Prompt Engineering (Part A):
- The function `generate_kyb_report` builds a system prompt that instructs the LLM to act as an expert KYB analyst.
- It sends a combined prompt with company details to the Groq API and expects a JSON-formatted response.

### Data Scraping for Enrichment (Part B):
- The function `scrape_additional_data` fetches the target company's website and extracts additional information (like an "About Us" summary) using BeautifulSoup.

### Main Workflow (Part C):
- The `main()` function demonstrates a sample workflow: generating a KYB report via the Groq API, scraping additional data, and merging both datasets into a final enriched profile.

## Use Cases

- Vendor due diligence
- Partnership evaluation
- Investment research
- Compliance verification
- Risk assessment

## Implementation Notes

This system can be integrated with:
- Company registries APIs
- Financial databases
- News and sanctions screening services
- Business credit reporting agencies