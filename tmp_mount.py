import sys
sys.path.insert(0, "/app")

import A2AServer.v2.admin_api as aa
print("admin_api loaded, routes:", len(aa.router.routes))

from A2AServer.v2 import oauth2
print("oauth2 loaded")

from A2AServer.v2 import user_store
print("user_store loaded")

print("All imports OK")
