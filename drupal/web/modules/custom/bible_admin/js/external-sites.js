/**
 * @file
 * The External sites page's Open buttons (2026-11-19): each site opens in its own browser window, placed beside this
 * one and taking about 60% of the screen's width, so a site that needs a sign-in (the Kindle web reader) is signed in
 * there as usual. It is never shown in a frame: Amazon refuses to show its sign-in inside another site, and a framed
 * site gets none of its own cookies. The new window's way back to this page (window.opener) is cut. When the browser
 * blocks the window, the link itself opens the site in a new tab (target _blank, rel noopener). A site's Sign in button
 * (when it has a sign-in address) opens that page in the same window.
 */
((Drupal, once) => {
  Drupal.behaviors.bibleAdminExternalSites = {
    attach(context) {
      once('external-site-open', 'a[data-external-site]', context).forEach((link) => {
        link.addEventListener('click', (event) => {
          const screenWidth = window.screen.availWidth || 1280;
          const screenHeight = window.screen.availHeight || 900;
          const width = Math.max(480, Math.round(screenWidth * 0.6));
          const left = Math.max(0, (window.screen.availLeft || 0) + screenWidth - width);
          const top = window.screen.availTop || 0;
          // One window per site (its name), so Open and Sign in use the same one when the browser allows it.
          const opened = window.open('about:blank', `external-site-${link.dataset.externalSite}`, `popup,width=${width},height=${screenHeight},left=${left},top=${top}`);
          if (!opened) {
            // Blocked: the link goes on to open a new tab.
            return;
          }
          event.preventDefault();
          opened.opener = null;
          opened.location.href = link.href;
        });
      });
    },
  };
})(Drupal, once);
