// Empty stub for @copilotkit/a2ui-renderer — we don't use CopilotPopup,
// so this whole package is unused. Alias to here to avoid bundling its
// @a2ui/web_core imports.

const handler = {
  get(target, prop) {
    if (prop === Symbol.toPrimitive) return () => "";
    if (prop === "__esModule") return true;
    return new Proxy(function () {}, handler);
  },
};

const stub = new Proxy({}, handler);

export default stub;

// react-core specific imports
export const A2UIProvider = stub;
export const A2UIRenderer = stub;
export const A2UI_SCHEMA_CONTEXT_DESCRIPTION = "";
export const DEFAULT_SURFACE_ID = "default";
export const buildCatalogContextValue = () => stub;
export const extractCatalogComponentSchemas = () => stub;
export const initializeDefaultCatalog = () => stub;
export const injectStyles = () => {};
export const useA2UIActions = () => stub;
export const useA2UIError = () => null;
export const viewerTheme = stub;

// react-ui / runtime imports
export const CopilotPopup = stub;
export const A2uiSurface = stub;
export const createCatalog = () => stub;
export const registerDefaultCatalog = () => stub;
export const defaultTheme = stub;
export const litTheme = stub;
export const Catalog = stub;
export const ComponentContext = stub;
export const MessageProcessor = stub;
export const GenericBinder = stub;
