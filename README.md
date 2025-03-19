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
  ],
  "web_data": {
    "about_info": "String - Company description from website",
    "leadership_info": "Array - Leadership team information",
    "contact_info": "String - Contact information",
    "social_media": "Object - Social media links",
    "potential_risks": "Array - Potential risk indicators from website"
  },
  "news_data": {
    "news_search_performed": "Boolean - Whether news search was performed",
    "note": "String - Information about news search"
  }
}
```

## Explanation of the Python Script (v3)

### Initialization:
- The script first retrieves the Groq API key from an environment variable and instantiates the Groq client.
- (Refer to Groq's documentation for setting up your API key.)

### Advanced Prompt Engineering (Part A):
- The function `generate_kyb_report` builds a system prompt that instructs the LLM to act as an expert KYB analyst.
- It sends a combined prompt with company details to the Groq API and expects a JSON-formatted response.
- Enhanced to specifically request beneficial owners with ownership percentages and detailed risk indicators.
- Includes robust JSON parsing with fallback mechanisms.

### Data Scraping for Enrichment (Part B):
- The function `scrape_additional_data` fetches the target company's website and extracts additional information using BeautifulSoup:
  - About Us information
  - Leadership team details
  - Contact information
  - Social media links
  - Potential risk indicators through keyword scanning

### News Search (Part C):
- The function `search_news_for_risks` provides a placeholder for news article analysis.
- In a production environment, this would connect to a news API to identify potential risks.

### Main Workflow (Part D):
- The `main()` function demonstrates a sample workflow:
  1. Generating a KYB report via the Groq API
  2. Scraping additional data from the company website
  3. Searching for news about the company
  4. Merging all datasets into a final enriched profile
  5. Enhancing beneficial owners with leadership info when beneficial owners data is missing
  6. Enhancing risk indicators with potential risks detected from website content
  7. Saving the final report to a JSON file

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

## New Features in v3

1. **Enhanced Beneficial Owner Extraction**: Improved extraction of beneficial owners with ownership percentages.
2. **Risk Indicator Detection**: Scans website content for potential risk keywords and extracts context.
3. **Leadership Information**: Extracts leadership team information from company websites.
4. **Social Media Detection**: Identifies and extracts links to company social media profiles.
5. **News Search Integration**: Placeholder for integrating news API searches for risk analysis.
6. **Robust JSON Handling**: Better handling of JSON parsing with fallback mechanisms.
7. **Data Enrichment**: Combines AI-generated data with web scraping for a more complete profile.
8. **Contextual Risk Analysis**: Extracts context around risk keywords for better understanding.
