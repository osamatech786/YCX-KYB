import os
import json
import requests
import re
from bs4 import BeautifulSoup
import streamlit as st
from groq import Groq
import pandas as pd
from datetime import datetime
import glob
from crewai import Agent, Task, Crew, Process
import sys
import subprocess
from crewai.tools.base_tool import BaseTool  # Use CrewAI's BaseTool
import litellm  # For configuring Groq LLM with CrewAI

# Disable CrewAI telemetry to avoid timeout errors
os.environ["CREWAI_TELEMETRY"] = "false"
print(f"CREWAI_TELEMETRY set to: {os.environ.get('CREWAI_TELEMETRY')}")

# File paths (updated for Windows)
CORE_DATASET_PATH = os.path.join("C:", "Users", "prokh", "Desktop", "git projects", "YCX-KYB", "knowYourAi - Company Details.csv")
USER_OUTPUT_PATH = os.path.join("C:", "Users", "prokh", "Desktop", "git projects", "YCX-KYB", "user_output.csv")
REPORTS_DIR = os.path.join("C:", "Users", "prokh", "Desktop", "git projects", "YCX-KYB", "generated_reports")

# Create reports directory if it doesn't exist
os.makedirs(REPORTS_DIR, exist_ok=True)

# Set page config
st.set_page_config(
    page_title="KYB Due Diligence Tool",
    page_icon="🔍",
    layout="wide"
)

# App title and description
st.title("Know Your Business (KYB) Due Diligence Tool")
st.markdown("""
This application helps you perform KYB due diligence by gathering information about a company
from various sources and presenting it in a structured format.
""")

# Initialize session state
if 'admin_logged_in' not in st.session_state:
    st.session_state.admin_logged_in = False
if 'core_df' not in st.session_state:
    st.session_state.core_df = None

# Input method selection
input_choice = st.radio(
    "Choose your input method:",
    ["Enter Company Name", "Write Custom Prompt", "Admin View"]
)

# Simplified model_options with only the confirmed working models
model_options = {
    "LLaMA 3 70B": "llama3-70b-8192",
    "LLaMA 3 8B": "llama3-8b-8192",
    "LLaMA 3.3 70B Versatile": "llama-3.3-70b-versatile",
    "Mistral Saba 24B": "mistral-saba-24b"
}

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    
    selected_model = st.selectbox("Select AI Model", list(model_options.keys()))
    
    api_key = st.text_input("Enter your Groq API Key", type="password")
    st.markdown("[Generate Groq API Key](https://console.groq.com/keys)")
    
    company_name = st.text_input("Company Name (Optional)", help="Enter for single company report.")
    company_website = st.text_input("Company Website (Optional)", help="Optional for single company report.")
    custom_prompt = st.text_area("Special Instructions (Optional)", help="E.g., 'Look for companies whose name starts with M'")
    
    run_button = st.button("Generate Report", type="primary")

# First, define all the basic functions
def scrape_web_for_company(company_name):
    """Enhanced web scraping for company information"""
    try:
        # Search multiple sources
        sources = [
            f"https://www.google.com/search?q={company_name}+company+registration+information",
            f"https://www.google.com/search?q={company_name}+financial+results+annual+report",
            f"https://www.google.com/search?q={company_name}+executives+management+team",
            f"https://www.google.com/search?q={company_name}+news+recent+developments"
        ]
        
        all_data = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        for search_url in sources:
            try:
                res = requests.get(search_url, headers=headers, timeout=15)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, 'html.parser')

                # Try multiple selectors to find search snippets
                snippets = []
                # Selector 1: Common Google search result snippet class
                for selector in [
                    ('div', {'class': 'BNeawe s3v9rd AP7Wnd'}),
                    ('div', {'class': 'BNeawe vvjwJb AP7Wnd'}),  # Title of the result
                    ('span', {'class': 'aCOpRe'}),  # Description snippet
                    ('div', {'class': 'VwiC3b yXK7lf lVm3ye r025kc hJNv7e'})  # Another common snippet class
                ]:
                    elements = soup.find_all(selector[0], selector[1])
                    snippets.extend([element.get_text(separator=" ", strip=True) for element in elements if element.get_text().strip()])

                # If no snippets found, try extracting text from the main content area
                if not snippets:
                    main_content = soup.find('div', {'id': 'main'})
                    if main_content:
                        snippets.extend([main_content.get_text(separator=" ", strip=True)[:500]])

                # Filter out empty snippets and join
                text = ' '.join([snippet for snippet in snippets if snippet])
                if text:
                    all_data.append(text)
            except Exception as e:
                st.warning(f"Failed to scrape {search_url}: {str(e)}")
                continue
        
        combined_data = ' '.join(all_data)
        return combined_data if combined_data else "No additional data found from web scraping."
        
    except Exception as e:
        return f"Error scraping web: {str(e)}"

def process_data_with_llm(text, api_key, model):
    """Process the scraped data using Groq API."""
    try:
        client = Groq(api_key=api_key)
        
        system_prompt = """
        You are a data analyst tasked with converting unstructured company data into a structured format.

        Take the input under 'raw_text' and extract:
        - summary
        - key_findings
        - risk_factors

        Respond ONLY with a valid JSON object like:
        {
        "summary": "Short summary...",
        "key_findings": ["fact1", "fact2"],
        "risk_factors": ["risk1", "risk2"]
        }

        Don't include explanations or extra text. Use double quotes. Escape problematic characters.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this company information: {text}"}
        ]
        
        response = client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=1024
        )
        
        output_text = response.choices[0].message.content
        return output_text
        
    except Exception as e:
        return f"Error processing data: {str(e)}"

def save_to_core_dataset(company_name, processed_data):
    """Save the processed data into the core dataset CSV."""
    try:
        new_data = pd.DataFrame({
            "company_name": [company_name],
            "additional_info": [processed_data],
            "timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        })
        if os.path.exists(CORE_DATASET_PATH):
            existing_data = pd.read_csv(CORE_DATASET_PATH)
            updated_data = pd.concat([existing_data, new_data], ignore_index=True)
        else:
            updated_data = new_data
        updated_data.to_csv(CORE_DATASET_PATH, index=False)
        return f"Data saved to {CORE_DATASET_PATH}"
    except Exception as e:
        return f"Error saving to CSV: {str(e)}"

# Define custom tools by inheriting from BaseTool with proper type annotations
class WebScraperTool(BaseTool):
    name: str = "Web Scraper"
    description: str = "Scrapes company information from the web"

    def _run(self, company_name: str) -> str:
        return scrape_web_for_company(company_name)
    
    def _arun(self, company_name: str) -> str:
        # Async version - can be same as _run for now
        return self._run(company_name)

class DataProcessorTool(BaseTool):
    name: str = "Data Processor"
    description: str = "Processes and analyzes company data"

    def _run(self, text: str) -> str:
        return process_data_with_llm(text, api_key, model_options[selected_model])
    
    def _arun(self, text: str) -> str:
        return self._run(text)

class DataSaverTool(BaseTool):
    name: str = "Data Saver"
    description: str = "Saves processed data to CSV"

    def _run(self, company_name_and_data: tuple) -> str:
        company_name, processed_data = company_name_and_data
        return save_to_core_dataset(company_name, processed_data)
    
    def _arun(self, company_name_and_data: tuple) -> str:
        return self._run(company_name_and_data)

# Create tool instances
scraper_tool = WebScraperTool()
processor_tool = DataProcessorTool()
saver_tool = DataSaverTool()

# Define agents with the proper tool instances and Groq LLM
def create_agents(api_key, model):
    from crewai import LLM  # Import CrewAI's LLM class

    # Create an LLM instance using CrewAI's LLM class
    groq_llm = LLM(
        model=f"groq/{model}",  # Explicitly specify the provider as 'groq'
        api_key=api_key,
        temperature=0.1,
        max_tokens=1024
    )

    scraper_agent = Agent(
        role="Web Scraper",
        goal="Find comprehensive information about the company from reliable sources.",
        backstory="""You are an expert web scraper specialized in finding accurate company 
        information from various sources. You're known for your ability to gather detailed 
        business intelligence.""",
        tools=[scraper_tool],
        verbose=True,
        allow_delegation=False,
        llm=groq_llm  # Pass the Groq LLM
    )

    processor_agent = Agent(
        role="Data Analyst",
        goal="Analyze and structure company information into useful insights.",
        backstory="""You are a skilled data analyst with expertise in processing and 
        analyzing company information. You excel at identifying key business metrics 
        and risk factors.""",
        tools=[processor_tool],
        verbose=True,
        allow_delegation=False,
        llm=groq_llm  # Pass the Groq LLM
    )

    writer_agent = Agent(
        role="Data Engineer",
        goal="Save and organize company information in a structured format.",
        backstory="""You are a detail-oriented data engineer who ensures all company 
        information is properly stored and organized.""",
        tools=[saver_tool],
        verbose=True,
        allow_delegation=False,
        llm=groq_llm  # Pass the Groq LLM
    )

    return scraper_agent, processor_agent, writer_agent

# Then define the crew analysis function
def run_crew_analysis(company_name, api_key, model):
    """Run the CrewAI workflow for company analysis"""
    try:
        # First, test the Groq API directly
        st.write("Testing Groq API connection...")
        test_client = Groq(api_key=api_key)
        try:
            test_response = test_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": "Hello, are you working?"},
                ]
            )
            st.success("Test LLM response succeeded")
            st.write(test_response.choices[0].message.content)
        except Exception as e:
            st.error(f"Test Groq LLM failed: {str(e)}")
            return None

        # Create agents with the Groq LLM
        scraper_agent, processor_agent, writer_agent = create_agents(api_key, model)

        # Define tasks with more specific instructions
        scraping_task = Task(
            description=f"""Search for detailed information about {company_name}, including:
            - Company registration details
            - Financial information
            - Key executives and beneficial owners
            - Recent news and developments
            - Any risk indicators or regulatory issues

            Format your output as a JSON object like this:
            {{
                "raw_text": "<consolidated extracted text>"
            }}

            Ensure the string is enclosed in double quotes and properly escaped.
            """,
            agent=scraper_agent,
            expected_output="JSON object with a 'raw_text' field containing all discovered info",
            max_iterations=3
        )

        processing_task = Task(
            description="""Analyze the 'raw_text' field from the previous task and extract:
            - summary
            - key_findings
            - risk_factors

        Return your analysis ONLY as valid JSON, with this structure:
        {
        "summary": "...",
        "key_findings": [...],
        "risk_factors": [...]
        }

        Avoid extra commentary or explanation.
        """,
            agent=processor_agent,
            expected_output="Structured and analyzed company data in JSON format",
            context=[scraping_task]
        )

        saving_task = Task(
            description=f"Save the processed information for {company_name} in a structured format",
            agent=writer_agent,
            expected_output="Confirmation of data being saved",
            context=[processing_task],
            function=lambda processed_data: (company_name, processed_data)
        )

        # Create and run the crew with sequential process
        crew = Crew(
            agents=[scraper_agent, processor_agent, writer_agent],
            tasks=[scraping_task, processing_task, saving_task],
            verbose=True,
            process=Process.sequential
        )

        # Run the crew and add debugging information
        result = crew.kickoff(inputs={"company_name": company_name})
        
        # Debug the result
        if result is None:
            st.warning("Crew returned None. Debugging further...")
            st.write(f"Scraper Agent LLM: {scraper_agent.llm}")
            st.write(f"Model Used: {model}")
            st.write(f"Company Name: {company_name}")
            return "No additional data found from CrewAI analysis."
            
        if result.strip() == "":
            st.warning("CrewAI analysis returned empty result.")
            return "No additional data found from CrewAI analysis."
            
        return result

    except Exception as e:
        st.error(f"CrewAI workflow failed: {str(e)}")
        st.write("Full error details:", str(e))
        return f"Error in CrewAI workflow: {str(e)}"

# Function definitions
def generate_kyb_report(company_name, company_website, api_key, model):
    """Generate a KYB report using the selected Groq model with a fallback to web scraping."""
    client = Groq(api_key=api_key)
    system_prompt = (
        "You are a seasoned business analyst with expertise in KYB due diligence. "
        "When given a company name and website, research and summarize the following: "
        "registration number, incorporation date, beneficial owners, key financial metrics (e.g., revenue, net income, total assets), "
        "and public risk indicators (e.g., legal issues, sanctions). "
        "If specific details are not available, search for general information about the company, such as its founding year, leadership team, "
        "recent news, or financial performance indicators. "
        "Output ONLY a valid JSON object with keys: company_name, registration_number, incorporation_date, "
        "beneficial_owners, financial_summary, risk_indicators. Ensure the JSON is properly formatted "
        "with correct commas and quotes. Use 'Not publicly available' for missing data."
    )
    
    user_prompt = f"Company Name: {company_name}\nWebsite: {company_website or 'N/A'}\n\n"
    user_prompt += "Please research the company and provide information in valid JSON format. Ensure all JSON syntax is correct."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        with st.spinner(f"Generating report using {model}..."):
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=1024
            )
            
        output_text = response.choices[0].message.content
        
        output_text = output_text.strip()
        if output_text.startswith("```json"):
            output_text = output_text.replace("```json", "").replace("```", "")
        
        output_text = output_text.replace("'", '"')
        output_text = re.sub(r',\s*}', '}', output_text)
        output_text = re.sub(r',\s*]', ']', output_text)
        
        try:
            kyb_report = json.loads(output_text)
        except json.JSONDecodeError as e:
            st.error(f"JSON parsing error: {str(e)}")
            st.text("Raw response:")
            st.code(output_text)
            return None
        
        # Check if the report has mostly "Not publicly available" fields
        has_data = False
        for key in ["registration_number", "incorporation_date"]:
            if kyb_report.get(key, "Not publicly available") != "Not publicly available":
                has_data = True
                break
        if kyb_report.get("beneficial_owners", []) or kyb_report.get("risk_indicators", []):
            has_data = True
        if kyb_report.get("financial_summary", {}).get("revenue", "Not publicly available") != "Not publicly available":
            has_data = True

        # If the report lacks data, use the Web Scraper as a fallback
        if not has_data:
            st.warning("Groq API returned limited data. Falling back to web scraping...")
            scraped_data = scrape_web_for_company(company_name)
            if scraped_data and "No additional data found" not in scraped_data:
                # Process the scraped data to extract relevant information
                additional_info = {
                    "company_name": company_name,
                    "registration_number": "Not publicly available",
                    "incorporation_date": "Not publicly available",
                    "beneficial_owners": [],
                    "financial_summary": {"revenue": "Not publicly available", "net_income": "Not publicly available", "total_assets": "Not publicly available"},
                    "risk_indicators": []
                }

                # Extract incorporation date (e.g., "founded in 2023")
                date_match = re.search(r'(?:founded|established|incorporated)\s*(?:in)?\s*(\d{4})', scraped_data, re.IGNORECASE)
                if date_match:
                    additional_info["incorporation_date"] = date_match.group(1)

                # Extract financial data (e.g., "revenue of $100M")
                revenue_match = re.search(r'revenue\s*(?:of)?\s*\$?([\d,.]+)\s*(million|billion)?', scraped_data, re.IGNORECASE)
                if revenue_match:
                    amount = revenue_match.group(1).replace(",", "")
                    unit = revenue_match.group(2).lower() if revenue_match.group(2) else "unknown"
                    if unit == "million":
                        additional_info["financial_summary"]["revenue"] = f"${amount}M"
                    elif unit == "billion":
                        additional_info["financial_summary"]["revenue"] = f"${amount}B"
                    else:
                        additional_info["financial_summary"]["revenue"] = f"${amount}"

                # Extract beneficial owners (e.g., "CEO John Doe")
                owner_match = re.search(r'(CEO|Founder|Owner)\s*([A-Z][a-z]+\s[A-Z][a-z]+)', scraped_data, re.IGNORECASE)
                if owner_match:
                    additional_info["beneficial_owners"] = [owner_match.group(2)]

                # Extract risk indicators (e.g., "lawsuit", "sanction")
                if any(keyword in scraped_data.lower() for keyword in ["lawsuit", "sanction", "fraud", "regulatory issue"]):
                    additional_info["risk_indicators"] = ["Potential legal or regulatory issues identified"]

                # Merge the scraped data into the KYB report
                for key in additional_info:
                    if key in kyb_report and additional_info[key] and additional_info[key] != "Not publicly available" and additional_info[key] != []:
                        kyb_report[key] = additional_info[key]

        # Ensure the report has the required structure
        kyb_report = {
            "company_name": company_name,
            "registration_number": kyb_report.get("registration_number", "Not publicly available"),
            "incorporation_date": kyb_report.get("incorporation_date", "Not publicly available"),
            "beneficial_owners": kyb_report.get("beneficial_owners", []),
            "financial_summary": kyb_report.get("financial_summary", {}),
            "risk_indicators": kyb_report.get("risk_indicators", [])
        }
        
        if not isinstance(kyb_report["beneficial_owners"], list):
            kyb_report["beneficial_owners"] = [kyb_report["beneficial_owners"]] if kyb_report["beneficial_owners"] != "Not publicly available" else []
            
        if not isinstance(kyb_report["risk_indicators"], list):
            kyb_report["risk_indicators"] = [kyb_report["risk_indicators"]] if kyb_report["risk_indicators"] != "Not publicly available" else []
            
        if not isinstance(kyb_report["financial_summary"], dict):
            kyb_report["financial_summary"] = {"details": str(kyb_report["financial_summary"])}
            
        return kyb_report
        
    except Exception as e:
        st.error(f"Failed to generate report: {str(e)}")
        return None

def scrape_additional_data(company_website):
    """Scrape additional data from the company website."""
    if not company_website:
        return {"about_info": "N/A"}
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'}
        res = requests.get(company_website, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        about_text = ""
        for selector in [
            soup.find(id=lambda x: x and 'about' in x.lower()),
            soup.find("section", {"class": lambda x: x and 'about' in x.lower()}),
            soup.find("div", {"class": lambda x: x and 'about' in x.lower()}),
            soup.find(string=lambda text: text and 'About Us' in text)
        ]:
            if selector and hasattr(selector, 'get_text'):
                about_text = selector.get_text(separator=" ", strip=True)
                break
            elif selector and selector.parent:
                about_text = selector.parent.get_text(separator=" ", strip=True)
                break
        if not about_text:
            meta_desc = soup.find("meta", {"name": "description"})
            about_text = meta_desc.get("content") if meta_desc else soup.get_text(separator=" ", strip=True)[:500] + "..."
        return {"about_info": about_text[:500]}
    except Exception as e:
        st.error(f"Scraping failed: {str(e)}")
        return {"about_info": "Failed to retrieve data"}

def save_report(company_name, report_data):
    """Save report to JSON file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{company_name.replace(' ', '_')}_{timestamp}.json"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, 'w') as f:
        json.dump(report_data, f, indent=2)

def update_user_output(api_key, input_type, input_text, timestamp):
    """Update user_output.csv with usage data"""
    data = {
        'api_key': [api_key],
        'input_type': [input_type],
        'input_text': [input_text],
        'timestamp': [timestamp]
    }
    new_entry = pd.DataFrame(data)
    
    try:
        if os.path.exists(USER_OUTPUT_PATH):
            df = pd.read_csv(USER_OUTPUT_PATH)
            df = pd.concat([df, new_entry], ignore_index=True)
        else:
            df = new_entry
        df.to_csv(USER_OUTPUT_PATH, index=False)
    except Exception as e:
        st.error(f"Failed to update user_output.csv: {e}")

def load_core_dataset():
    """Load core dataset if it exists."""
    try:
        if os.path.exists(CORE_DATASET_PATH):
            st.session_state.core_df = pd.read_csv(CORE_DATASET_PATH)
            return st.session_state.core_df
        return None
    except Exception as e:
        st.error(f"Failed to load core dataset: {str(e)}")
        return None

# Define the display_report function before it's called
def display_report(report_data):
    """Display the KYB report in a structured format"""
    st.header("KYB Report")
    
    # Basic Information
    st.subheader("Basic Information")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Company Name:** {report_data.get('company_name', 'N/A')}")
        st.write(f"**Registration Number:** {report_data.get('registration_number', 'N/A')}")
    with col2:
        st.write(f"**Incorporation Date:** {report_data.get('incorporation_date', 'N/A')}")
    
    # Financial Summary
    st.subheader("Financial Summary")
    financial_summary = report_data.get('financial_summary', {})
    if isinstance(financial_summary, dict):
        for key, value in financial_summary.items():
            st.write(f"**{key.replace('_', ' ').title()}:** {value}")
    else:
        st.write(financial_summary)
    
    # Beneficial Owners
    st.subheader("Beneficial Owners")
    beneficial_owners = report_data.get('beneficial_owners', [])
    if beneficial_owners:
        for owner in beneficial_owners:
            if isinstance(owner, dict):
                st.write(f"- **{owner.get('name', 'Unknown')}** ({owner.get('ownership_percentage', 'Unknown')})")
            else:
                st.write(f"- {owner}")
    else:
        st.write("No beneficial owners information available")
    
    # Risk Indicators
    st.subheader("Risk Indicators")
    risk_indicators = report_data.get('risk_indicators', [])
    if risk_indicators:
        for risk in risk_indicators:
            st.write(f"- {risk}")
    else:
        st.write("No risk indicators identified")
    
    # Raw JSON
    with st.expander("View Raw JSON"):
        st.json(report_data)

# Placeholder for process_prompt (since it's not defined)
def process_prompt(prompt, df, api_key, model):
    """Process a custom prompt using the Groq API and return results as a DataFrame."""
    try:
        client = Groq(api_key=api_key)
        system_prompt = """
        You are a data analyst. Based on the given prompt, search for relevant company information
        and return the results in a structured format suitable for a DataFrame.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        response = client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=0.1,
            max_tokens=1024
        )
        output_text = response.choices[0].message.content
        
        # For simplicity, let's assume the response is a JSON string that can be converted to a DataFrame
        try:
            data = json.loads(output_text)
            return pd.DataFrame(data)
        except json.JSONDecodeError:
            st.error("Failed to parse prompt response as JSON.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error processing prompt: {str(e)}")
        return pd.DataFrame()

# Main logic section
if input_choice == "Admin View":
    with st.form("admin_login"):
        st.subheader("Admin Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if username == "ycxadmin" and password == "ycxadmin":
                st.session_state.admin_logged_in = True
                st.success("Logged in as admin!")
            else:
                st.error("Invalid credentials.")

elif input_choice == "Enter Company Name" and run_button:
    try:
        if not api_key:
            st.error("Please enter your Groq API Key.")
        elif not company_name:
            st.error("Please enter a Company Name.")
        else:
            # Load core dataset
            df = load_core_dataset()
            
            # Run CrewAI analysis with API key and model
            with st.spinner("Running CrewAI analysis..."):
                crew_result = run_crew_analysis(
                    company_name, 
                    api_key, 
                    model_options[selected_model]
                )
                if crew_result:
                    st.success("CrewAI analysis completed!")
                    st.write("Additional data gathered:", crew_result)
            
            # Generate KYB report
            with st.spinner(f"Processing {company_name}..."):
                kyb_report = generate_kyb_report(
                    company_name=company_name,
                    company_website=company_website,
                    api_key=api_key,
                    model=model_options[selected_model]
                )
                if kyb_report:
                    save_report(company_name, kyb_report)
                    update_user_output(
                        api_key=api_key,
                        input_type="company_name",
                        input_text=company_name,
                        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    display_report(kyb_report)
    except Exception as e:
        st.error(f"Error: {e}")

elif input_choice == "Write Custom Prompt" and run_button:
    try:
        if not api_key:
            st.error("Please enter your Groq API Key.")
        elif not custom_prompt:
            st.error("Please enter your prompt.")
        else:
            result_df = process_prompt(custom_prompt, None, api_key, model_options[selected_model])
            if result_df is not None and not result_df.empty:
                st.success("Results found!")
                st.dataframe(result_df, use_container_width=True)
            else:
                st.warning("No results from prompt.")
    except Exception as e:
        st.error(f"Error processing prompt: {e}")

else:
    if not st.session_state.admin_logged_in:
        st.info("Select an input method and click 'Generate Report' to proceed.")