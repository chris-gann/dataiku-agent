"""
Intelligent fallback response generation for common Dataiku issues.

Provides helpful fallback responses when search fails or returns insufficient results.
"""

def generate_fallback_response(query: str) -> str:
    """
    Generate intelligent fallback responses for common Dataiku issues when search fails.
    
    Args:
        query: User's original query
        
    Returns:
        Helpful fallback response
    """
    query_lower = query.lower()
    
    # Permission and profile issues
    if any(phrase in query_lower for phrase in ["not allowed", "permission", "profile", "visual machine learning", "prediction model"]):
        return """🔒 **Dataiku User Profile & Permissions Issue**

This error occurs when your user profile doesn't have the necessary permissions for Visual Machine Learning features.

**Immediate Solutions:**
• Contact your Dataiku administrator to request a profile upgrade
• Ask to be assigned to a group with "Data Scientist" or "ML Practitioner" permissions
• Check if your organization has Visual ML licenses available

**Profile Types in Dataiku:**
• **Reader**: Can view projects and dashboards
• **Analyst**: Can create basic recipes and datasets  
• **Data Scientist**: Can use Visual ML, code recipes, and advanced features
• **Admin**: Full platform access

**Common Causes:**
• License limitations in your Dataiku instance
• Restrictive user group assignments
• Organization policy restrictions

💡 **Tip**: Most Visual ML features require "Data Scientist" level permissions or higher."""

    # Authentication issues
    elif any(phrase in query_lower for phrase in ["authentication", "login", "access denied", "unauthorized"]):
        return """🔐 **Dataiku Authentication Issue**

**Common Solutions:**
• Clear browser cache and cookies for Dataiku
• Try logging in with incognito/private browsing mode
• Check with your admin about LDAP/SSO configuration
• Verify your username and password are correct
• Check if your account has been deactivated

**If using SSO:**
• Ensure you're accessing Dataiku through the correct SSO portal
• Contact your IT team about SSO token expiration"""

    # Dataset/connection issues  
    elif any(phrase in query_lower for phrase in ["dataset", "connection", "cannot connect", "data source"]):
        return """📊 **Dataiku Dataset/Connection Issue**

**Troubleshooting Steps:**
• Check dataset connection settings in the dataset settings page
• Verify database credentials and network connectivity
• Test the connection using "Test & Get Schema"
• Check if the source system is available and accessible
• Review connection logs for detailed error messages

**Common Causes:**
• Expired database credentials
• Network/firewall restrictions
• Source system maintenance or downtime
• Changed schema or table structure"""

    # Recipe/job failures
    elif any(phrase in query_lower for phrase in ["recipe failed", "job failed", "build failed", "error in recipe"]):
        return """⚙️ **Dataiku Recipe/Job Failure**

**Debugging Steps:**
• Check the job logs for detailed error messages
• Review the recipe configuration and input datasets
• Verify all required columns are present in input data
• Check for data quality issues (nulls, formatting, etc.)
• Ensure sufficient compute resources are available

**Common Solutions:**
• Refresh input dataset schemas
• Clear recipe cache and rebuild
• Check SQL syntax in SQL recipes
• Verify Python/R code syntax in code recipes"""

    # Performance issues
    elif any(phrase in query_lower for phrase in ["slow", "performance", "timeout", "hanging"]):
        return """⚡ **Dataiku Performance Issue**

**Optimization Tips:**
• Use dataset sampling for large datasets during development
• Add appropriate filters to reduce data volume
• Consider using database pushdown for SQL operations
• Check cluster resource allocation
• Review recipe memory and CPU settings

**For Visual Recipes:**
• Use "Limit" step to work with smaller datasets
• Optimize Join operations (use appropriate join types)
• Consider partitioning large datasets"""

    # General fallback
    else:
        return f"""🤖 **Dataiku Assistant - Search Temporarily Unavailable**

I'm having trouble searching for specific information about your query right now, but here are some general resources that might help:

**Quick Help:**
• Check the Dataiku Documentation: https://doc.dataiku.com/
• Visit Dataiku Community: https://community.dataiku.com/
• Contact your Dataiku administrator for account-specific issues
• Try rephrasing your question with more specific terms

**Your Query:** `{query[:200]}{'...' if len(query) > 200 else ''}`

Please try asking again in a few minutes, or contact your Dataiku administrator if this is urgent."""