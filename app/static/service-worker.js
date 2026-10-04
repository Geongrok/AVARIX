/* ============================================================
   AVARIX — PWA Service Worker
   ============================================================

   IMPORTANT:
   - API responses are NOT cached.
   - HTML/navigation is NOT cached.
   - Authentication/session data is NOT cached.
   - Only static frontend assets are cached.
   ============================================================ */

const CACHE_NAME = "avarix-static-v2";

const STATIC_ASSETS = [
    "/static/style.css",
    "/static/app.js",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
    "/static/icons/icon-512-maskable.png"
];


/* ------------------------------------------------------------
   INSTALL
   ------------------------------------------------------------ */

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});


/* ------------------------------------------------------------
   ACTIVATE
   ------------------------------------------------------------ */

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys()
            .then(keys => {
                return Promise.all(
                    keys
                        .filter(key => key !== CACHE_NAME)
                        .map(key => caches.delete(key))
                );
            })
            .then(() => self.clients.claim())
    );
});


/* ------------------------------------------------------------
   FETCH
   ------------------------------------------------------------ */

self.addEventListener("fetch", event => {

    const request = event.request;
    const url = new URL(request.url);

    /* Only handle same-origin GET requests. */
    if (
        request.method !== "GET" ||
        url.origin !== self.location.origin
    ) {
        return;
    }


    /*
     * NEVER intercept:
     *
     * /api/*
     * authenticated pages
     * navigation/document requests
     *
     * This is important for AVARIX authentication,
     * chat responses, logout and account information.
     */

    if (
        url.pathname.startsWith("/api/") ||
        request.mode === "navigate" ||
        request.destination === "document"
    ) {
        return;
    }


    /*
     * Static assets:
     *
     * Cache first
     * Network fallback
     */

    if (
        request.destination === "script" ||
        request.destination === "style" ||
        request.destination === "image" ||
        request.destination === "font" ||
        url.pathname.startsWith("/static/")
    ) {

        event.respondWith(

            caches.match(request)
                .then(cachedResponse => {

                    if (cachedResponse) {
                        return cachedResponse;
                    }

                    return fetch(request)
                        .then(networkResponse => {

                            /*
                             * Only cache successful responses.
                             */

                            if (
                                networkResponse &&
                                networkResponse.ok
                            ) {

                                const responseCopy =
                                    networkResponse.clone();

                                caches.open(CACHE_NAME)
                                    .then(cache => {
                                        cache.put(
                                            request,
                                            responseCopy
                                        );
                                    });
                            }

                            return networkResponse;
                        });

                })

        );
    }

});