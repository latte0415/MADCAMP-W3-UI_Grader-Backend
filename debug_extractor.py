
from services.element_extractor import ElementExtractor
import json

html = """
<html>
<body>
    <button id="btn-clear" class="btn-primary" disabled>
        Processing...
        <div id="spinner-clear" style="display: block;" class="my-custom-spinner">Loading...</div>
    </button>
</body>
</html>
"""

css = """
.my-custom-spinner {
    width: 20px;
    height: 20px;
    background: red;
}
"""

print("Running ElementExtractor debug...")
extractor = ElementExtractor(html, css)
result = extractor.extract()

print("Elements found:", len(result['elements']))
print("Status Components:", json.dumps(result['status_components'], indent=2, ensure_ascii=False))

indicators = result['status_components'].get('progress_indicators', [])
if indicators:
    print("\nSUCCESS: Spinner detected!")
else:
    print("\nFAILURE: Spinner NOT detected.")
    print("Selectors used in extractor: .spinner, .loader, .loading, .progress, [role='progressbar'], ...")
    print("The custom ID 'spinner-clear' or class 'my-custom-spinner' might not be covered.")
