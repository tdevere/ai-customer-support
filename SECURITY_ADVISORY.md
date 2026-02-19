# Security Advisory

## Date: 2024-02-18

## Critical Security Updates Applied

### Summary
This document outlines the security vulnerabilities that were identified and patched in the AAN Customer Support System dependencies.

## Vulnerabilities Fixed

### 1. LangChain Template Injection via Attribute Access
**Severity**: HIGH  
**CVE**: N/A (GitHub Advisory)  
**Affected Package**: `langchain-core`  
**Affected Versions**: 
- >= 1.0.0, <= 1.0.6
- <= 0.3.79

**Description**: LangChain was vulnerable to template injection attacks via attribute access in prompt templates, which could allow attackers to execute arbitrary code or access sensitive data.

**Previous Version**: 0.2.0 (VULNERABLE)  
**Patched Version**: 0.3.81 ✅  
**Action Taken**: Updated to 0.3.81

### 2. LangChain Serialization Injection Vulnerability
**Severity**: HIGH  
**CVE**: N/A (GitHub Advisory)  
**Affected Package**: `langchain-core`  
**Affected Versions**:
- >= 1.0.0, < 1.2.5
- < 0.3.81

**Description**: LangChain serialization injection vulnerability enabled secret extraction in dumps/loads APIs, potentially exposing API keys and other sensitive configuration data.

**Previous Version**: 0.2.0 (VULNERABLE)  
**Patched Version**: 0.3.81 ✅  
**Action Taken**: Updated to 0.3.81

## Additional Security Updates

### Related LangChain Ecosystem Updates
To maintain compatibility and security across the LangChain ecosystem:

- **langchain**: Updated from 0.2.0 → 0.3.15 (fixed langsmith dependency conflict)
- **langchain-openai**: Updated from 0.1.8 → 0.2.14
- **langgraph**: Updated from 0.2.0 → 0.2.60
- **langsmith**: Auto-resolved by pip (>=0.3.45,<1.0.0 per langchain-core requirements)

### Other Dependency Updates
The following dependencies were also updated to their latest stable versions for security and stability:

- **fastapi**: 0.110.0 → 0.115.6
- **uvicorn**: 0.27.1 → 0.34.0
- **pydantic**: 2.6.3 → 2.10.5
- **pydantic-settings**: 2.2.1 → 2.7.1
- **httpx**: 0.27.0 → 0.27.2
- **stripe**: 8.5.0 → 11.2.0
- **requests**: 2.31.0 → 2.32.4 (CVE fix)
- **azure-identity**: 1.15.0 → 1.16.1 (CVE fix)
- **black**: 24.2.0 → 24.3.0 (CVE fix)

## Impact Assessment

### Risk Level: HIGH
These vulnerabilities could potentially:
- Allow arbitrary code execution
- Enable secret extraction from serialized objects
- Compromise API keys and credentials
- Affect system integrity and confidentiality

### Affected Components
- All LangChain-based agents (Billing, Tech, Returns)
- Orchestrator (LangGraph workflows)
- Verifier agent
- Any component using LangChain prompt templates

### Exploitation Risk
- **Template Injection**: Requires attacker-controlled input to prompt templates
- **Serialization Injection**: Requires access to serialized objects or dumps/loads APIs

## Mitigation Status: ✅ RESOLVED

All vulnerable dependencies have been updated to patched versions. The system is now secure against the identified vulnerabilities.

## Verification Steps

To verify the security updates:

```bash
# 1. Check installed versions
pip list | grep langchain

# Expected output (minimum versions):
# langchain              0.3.15
# langchain-core         0.3.81
# langchain-openai       0.2.14
# langgraph              0.2.60
# langsmith              0.3.45+ (auto-resolved)

# 2. Run security scan
pip install safety
safety check

# 3. Run tests to ensure compatibility
pytest tests/ -v
```

## Deployment Recommendations

### Immediate Actions Required

1. **Update Dependencies**
   ```bash
   pip install -r requirements.txt --upgrade
   ```

2. **Test Application**
   ```bash
   pytest tests/ -v
   ```

3. **Redeploy**
   ```bash
   # Development
   func azure functionapp publish func-aan-support-dev

   # Production
   func azure functionapp publish func-aan-support-prod
   ```

4. **Verify in Production**
   - Check Azure Application Insights for errors
   - Monitor first 24 hours for anomalies
   - Verify agent responses are working correctly

### Rollback Plan
If issues occur after deployment:

```bash
# Revert to previous version
git revert HEAD
pip install -r requirements.txt
func azure functionapp publish <function-app-name>
```

## Prevention Measures

### Going Forward

1. **Automated Security Scanning**
   - GitHub Actions workflow includes Trivy security scanning
   - Dependabot alerts enabled for vulnerability notifications

2. **Regular Updates**
   - Review and update dependencies monthly
   - Subscribe to security advisories for critical packages
   - Monitor GitHub Security tab

3. **Testing**
   - Run full test suite before any dependency update
   - Perform security regression testing
   - Validate in staging before production

## References

- LangChain Security Advisories: https://github.com/langchain-ai/langchain/security/advisories
- Python Package Index (PyPI): https://pypi.org/
- OWASP Top 10: https://owasp.org/www-project-top-ten/

## Contact

For security concerns or questions:
- Create a GitHub Security Advisory
- Contact: security@example.com

---

**Status**: ✅ PATCHED  
**Last Updated**: 2024-02-18  
**Next Review**: 2024-03-18
