/**
 * 极简 hash 路由
 * 路由定义形如 { pattern: "files/:id", title: "文件详情", view: {...} }
 */
export function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [pathPart, queryPart] = raw.split("?");
  const segments = pathPart.split("/").filter(Boolean).map((part) => {
    try {
      return decodeURIComponent(part);
    } catch (_) {
      return part;
    }
  });
  const query = {};
  new URLSearchParams(queryPart || "").forEach((value, key) => {
    query[key] = value;
  });
  return { segments, query };
}

/** 按定义匹配当前 hash */
export function resolveRoute(definitions) {
  const { segments, query } = parseHash();
  for (const definition of definitions) {
    const patternParts = definition.pattern.split("/").filter(Boolean);
    if (patternParts.length !== segments.length) continue;
    const params = {};
    let matched = true;
    for (let i = 0; i < patternParts.length; i++) {
      const part = patternParts[i];
      if (part.startsWith(":")) {
        params[part.slice(1)] = segments[i];
      } else if (part !== segments[i]) {
        matched = false;
        break;
      }
    }
    if (matched) return { definition, params, query };
  }
  return { definition: null, params: {}, query };
}

/** 跳转（改变 hash 触发路由） */
export function navigate(path, query) {
  let hash = path.startsWith("#") ? path : "#" + (path.startsWith("/") ? path : "/" + path);
  if (query && typeof query === "object") {
    const search = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.append(key, String(value));
    });
    const text = search.toString();
    if (text) hash += (hash.includes("?") ? "&" : "?") + text;
  }
  if (location.hash === hash) return;
  location.hash = hash;
}

/** 当前 hash 对应的 path（不含 query） */
export function currentPath() {
  return "#" + parseHash().segments.join("/");
}
