/* Gedeelde, Nederlandstalige pushweergave voor de webapp en serviceworker. */
(() => {
  const BRANDING = 'https://jrlcofhpxvnlqzirjdbd.supabase.co/storage/v1/object/public/lcp-branding/';
  const DEFAULTS = Object.freeze({title:'LCP – Oproep',default_message:'Er is op de oproepknop gedrukt.',app_name:'LCP',icon_url:'./icon-512.png'});
  const text = (value, fallback, limit) => typeof value === 'string' && value.trim() ? value.trim().slice(0,limit) : fallback;
  function safeIcon(value) {
    if (typeof value !== 'string') return DEFAULTS.icon_url;
    if (['./icon-192.png','./icon-512.png'].includes(value)) return value;
    try {
      const url = new URL(value);
      if (url.href.startsWith(BRANDING) && url.pathname.endsWith('.png') && !url.search && !url.hash && !url.username && !url.password) return url.href;
    } catch {}
    return DEFAULTS.icon_url;
  }
  function normalize(value = {}) {
    value = value && typeof value === 'object' ? value : {};
    return {
      title:text(value.title,DEFAULTS.title,100),
      default_message:text(value.default_message,DEFAULTS.default_message,240),
      app_name:text(value.app_name,DEFAULTS.app_name,24),
      icon_url:safeIcon(value.icon_url),
      updated_at:typeof value.updated_at === 'string' ? value.updated_at : null,
    };
  }
  function validate(value) {
    for (const [key,max,label] of [['title',100,'Titel'],['default_message',240,'Standaardbericht'],['app_name',24,'Appnaam']]) {
      if (typeof value[key] !== 'string' || !value[key].trim() || value[key].trim().length > max) throw Error(`${label} moet 1 tot ${max} tekens bevatten.`);
    }
    if (safeIcon(value.icon_url) !== value.icon_url) throw Error('Kies een PNG-logo uit de LCP-opslag.');
    return normalize(value);
  }
  function notification(data, cached) {
    data = data && typeof data === 'object' ? data : {};
    // Nieuwe afzenders leveren actuele voorkeuren mee. Oudere afzenders blijven werken.
    const settings = normalize(data.lcp_preferences || cached);
    return {
      title:cached || data.lcp_preferences ? settings.title : text(data.title,settings.title,100),
      options:{body:text(data.message || data.body,settings.default_message,240),
        tag:'lcp-'+text(String(data.id || Date.now()),'oproep',100),
        icon:settings.icon_url,badge:'./icon-192.png',lang:'nl',
        data:{url:'./app.html'}},
    };
  }
  globalThis.LcpPush = Object.freeze({DEFAULTS,normalize,validate,safeIcon,notification});
})();
