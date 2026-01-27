#!/bin/bash
# Analytics Setup Script
# This script helps verify and configure analytics tracking

set -e

echo "============================================"
echo "CKAN Analytics Tracking Setup"
echo "============================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running in Docker
if [ -f /.dockerenv ]; then
    echo -e "${GREEN}✓${NC} Running inside Docker container"
    IN_DOCKER=true
else
    echo -e "${YELLOW}!${NC} Not running in Docker. Some checks will be skipped."
    IN_DOCKER=false
fi

echo ""
echo "--- Checking Environment Variables ---"

# Check RUDDERSTACK_ENABLED
if [ -z "$RUDDERSTACK_ENABLED" ]; then
    echo -e "${RED}✗${NC} RUDDERSTACK_ENABLED not set"
    echo "  Set in .env file: RUDDERSTACK_ENABLED=true"
elif [ "$RUDDERSTACK_ENABLED" = "true" ]; then
    echo -e "${GREEN}✓${NC} RUDDERSTACK_ENABLED=true"
else
    echo -e "${YELLOW}!${NC} RUDDERSTACK_ENABLED=$RUDDERSTACK_ENABLED (should be 'true')"
fi

# Check RUDDERSTACK_WRITE_KEY
if [ -z "$RUDDERSTACK_WRITE_KEY" ]; then
    echo -e "${RED}✗${NC} RUDDERSTACK_WRITE_KEY not set"
    echo "  Set in .env file: RUDDERSTACK_WRITE_KEY=your_write_key"
elif [ "$RUDDERSTACK_WRITE_KEY" = "your_write_key_here" ] || [ "$RUDDERSTACK_WRITE_KEY" = "<WRITE_KEY>" ]; then
    echo -e "${YELLOW}!${NC} RUDDERSTACK_WRITE_KEY is placeholder value"
    echo "  Get your actual write key from RudderStack dashboard"
else
    echo -e "${GREEN}✓${NC} RUDDERSTACK_WRITE_KEY is set"
fi

# Check RUDDERSTACK_DATA_PLANE_URL
if [ -z "$RUDDERSTACK_DATA_PLANE_URL" ]; then
    echo -e "${RED}✗${NC} RUDDERSTACK_DATA_PLANE_URL not set"
    echo "  Set in .env file: RUDDERSTACK_DATA_PLANE_URL=https://your-dataplane-url"
elif [ "$RUDDERSTACK_DATA_PLANE_URL" = "<DATA_PLANE_URL>" ]; then
    echo -e "${YELLOW}!${NC} RUDDERSTACK_DATA_PLANE_URL is placeholder value"
else
    echo -e "${GREEN}✓${NC} RUDDERSTACK_DATA_PLANE_URL=$RUDDERSTACK_DATA_PLANE_URL"
fi

echo ""
echo "--- Checking Files ---"

# Check if analytics files exist
FILES=(
    "/srv/app/src_extensions/ckanext-pidinst-theme/ckanext/pidinst_theme/assets/js/analytics-tracking.js"
    "/srv/app/src_extensions/ckanext-pidinst-theme/ckanext/pidinst_theme/analytics.py"
    "/srv/app/src_extensions/ckanext-pidinst-theme/ckanext/pidinst_theme/analytics_views.py"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} Found: $(basename $file)"
    else
        echo -e "${RED}✗${NC} Missing: $file"
    fi
done

echo ""
echo "--- Checking Python Dependencies ---"

if $IN_DOCKER; then
    if python -c "import rudderstack" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} rudderstack-python SDK installed"
    else
        echo -e "${YELLOW}!${NC} rudderstack-python SDK not installed"
        echo "  This is optional but enables server-side tracking"
        echo "  Install with: pip install rudderstack-python"
    fi
fi

echo ""
echo "--- Testing Analytics Initialization ---"

if $IN_DOCKER; then
    python << 'EOF'
import sys
try:
    from ckanext.pidinst_theme import analytics
    analytics.AnalyticsTracker.initialize()
    if analytics.AnalyticsTracker.is_enabled():
        print("\033[0;32m✓\033[0m Analytics tracker is enabled and initialized")
    else:
        print("\033[1;33m!\033[0m Analytics tracker initialized but disabled (check RUDDERSTACK_ENABLED)")
except Exception as e:
    print(f"\033[0;31m✗\033[0m Failed to initialize analytics: {e}")
    sys.exit(1)
EOF
fi

echo ""
echo "--- Quick Test Commands ---"
echo ""
echo "Test frontend tracking (in browser console):"
echo "  console.log(typeof window.CKANAnalytics);"
echo "  console.log(typeof rudderanalytics);"
echo ""
echo "Test backend tracking (in Python):"
echo "  from ckanext.pidinst_theme import analytics"
echo "  analytics.AnalyticsTracker.track('test_user', 'Test Event', {'test': 'data'})"
echo ""
echo "View logs:"
echo "  docker compose -f docker-compose.dev.yml logs -f ckan-dev | grep -i analytics"
echo ""
echo "Check RudderStack Live Events:"
echo "  https://app.rudderstack.com/ → Your Source → Live Events"
echo ""

echo "============================================"
echo "Setup Check Complete!"
echo "============================================"
