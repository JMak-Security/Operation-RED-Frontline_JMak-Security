import matplotlib.pyplot as plt
from fpdf import FPDF
import os

# --- CONFIGURATION & BRANDING ---
BRAND_NAME = "Mr. RED"
ACCENT_COLOR = (200, 0, 0)  # Red
BG_COLOR = (30, 30, 30)      # Dark Charcoal
TEXT_COLOR = (255, 255, 255) # White

class VulnerabilityReport(FPDF):
    def header(self):
        # Brand Header
        self.set_fill_color(*ACCENT_COLOR)
        self.rect(0, 0, 210, 25, 'F')
        self.set_font("Arial", 'B', 16)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, f"{BRAND_NAME} | SECURITY ASSESSMENT REPORT", 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", 'I', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Page {self.page_no()} - Confidential - {BRAND_NAME}", 0, 0, 'C')

    def section_title(self, label):
        self.set_font("Arial", 'B', 12)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(*ACCENT_COLOR)
        self.cell(0, 10, f"  {label}", 0, 1, 'L', fill=True)
        self.ln(4)

    def chapter_body(self, text):
        self.set_font("Arial", '', 10)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 6, text)
        self.ln()

def create_probability_graph(output_path):
    """Generates a Reproducible Probability Graph using Matplotlib."""
    attempts = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    probability = [0.1, 0.25, 0.45, 0.70, 0.85, 0.95, 1.0, 1.0, 1.0, 1.0]

    plt.figure(figsize=(6, 4))
    plt.plot(attempts, probability, marker='o', color='red', linestyle='-', linewidth=2)
    plt.fill_between(attempts, probability, color='red', alpha=0.1)
    
    plt.title("Reproducible Probability (Success Rate over Attempts)", fontsize=12, fontweight='bold')
    plt.xlabel("Execution Attempts", fontsize=10)
    plt.ylabel("Probability of Success", fontsize=10)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.ylim(0, 1.1)
    
    plt.savefig(output_path, bbox_inches='tight', dpi=150)
    plt.close()

def generate_report(author_name="____________________"):
    pdf = VulnerabilityReport()
    pdf.add_page()
    
    # 0. Title Page Info
    pdf.set_font("Arial", 'B', 24)
    pdf.set_text_color(40, 40, 40)
    pdf.ln(20)
    pdf.cell(0, 10, "VULNERABILITY FINDING REPORT", 0, 1, 'L')
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 10, f"Prepared by: {author_name}", 0, 1, 'L')
    pdf.ln(10)

    # 1. Executive Summary
    pdf.section_title("EXECUTIVE SUMMARY")
    pdf.chapter_body(
        "This report outlines a critical vulnerability identified during the security assessment. "
        "The flaw allows for unauthorized access to sensitive system components. Immediate remediation "
        "is recommended to prevent potential data exfiltration and service disruption."
    )

    # 2. Step-by-Step Recreation
    pdf.section_title("STEP-BY-STEP RECREATION")
    steps = (
        "1. Authenticate to the application using a low-privileged user account.\n"
        "2. Intercept the HTTP request sent to the /api/v1/user/settings endpoint.\n"
        "3. Modify the 'user_id' parameter to match a target administrative account.\n"
        "4. Forward the request and observe the administrative response returned to the attacker."
    )
    pdf.chapter_body(steps)

    # 3. Reproducible Probability Graph
    graph_filename = "prob_graph.png"
    create_probability_graph(graph_filename)
    pdf.section_title("REPRODUCIBLE PROBABILITY ANALYSIS")
    pdf.image(graph_filename, x=25, w=160)
    pdf.ln(5)
    pdf.chapter_body(
        "The graph above illustrates the likelihood of a successful exploit over multiple attempts. "
        "Due to race conditions or environmental factors, the vulnerability reaches a 100% success "
        "probability within 7 attempts."
    )

    # 4. Potential Impacts
    pdf.section_title("IMPACT ANALYSIS")
    
    impacts = [
        ("General Impact", "Broad risk to the integrity of the application platform."),
        ("Technical Impact", "Allows for Insecure Direct Object Reference (IDOR) and lateral movement."),
        ("Operational Impact", "May lead to system downtime if exploited at scale, affecting uptime SLAs."),
        ("Business Impact", "Potential loss of customer trust and regulatory non-compliance fines (GDPR/HIPAA).")
    ]

    for cat, desc in impacts:
        pdf.set_font("Arial", 'B', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(40, 7, f"{cat}:", 0, 0)
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 7, desc)
        pdf.ln(2)

    # Save and Cleanup
    report_name = "MrRed_Vulnerability_Report.pdf"
    pdf.output(report_name)
    if os.path.exists(graph_filename):
        os.remove(graph_filename)
    print(f"Report generated successfully: {report_name}")

if __name__ == "__main__":
    # You can enter your name here or leave it blank as requested
    generate_report(author_name="[ENTER YOUR NAME HERE]")