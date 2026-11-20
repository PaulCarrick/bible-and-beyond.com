/**
 * @file
 * A spinner and the percent sent while a form with a large file is sent (the song form of Christian music:
 * a video can be 1 GB and take minutes). When the form is submitted its buttons are turned off, so it cannot
 * be sent twice, and a line under them says "Uploading… 42%", then "Saving it…" while the server reads the
 * file.
 *
 * The form is sent with XMLHttpRequest (the only way to know how much has gone), marked with the header
 * X-Bible-Admin-Upload. After a save the form answers {"redirect": address} (MusicForm::submitForm) and the
 * page goes there, where Drupal shows its message. When the form is shown again with a problem, its page's
 * main part (the messages and the form) takes the place of this one's and Drupal's behaviors are attached to
 * it, as Drupal's own AJAX does. Where the browser cannot send it so, the form is sent the ordinary way, with
 * the spinner only. A lost connection or a server error puts the form back as it was, with a message.
 */
((Drupal, drupalSettings, once) => {
  function element(tag, className, text = '') {
    const made = document.createElement(tag);
    made.className = className;
    made.textContent = text;
    return made;
  }

  // Puts the main part of the page the server answered with in place of this one's. False when either has
  // none (the answer is then not a page of the admin theme).
  function showMainPart(html) {
    const answer = new DOMParser().parseFromString(html, 'text/html');
    const newMain = answer.querySelector('main');
    const oldMain = document.querySelector('main');
    if (!newMain || !oldMain) {
      return false;
    }
    const imported = document.importNode(newMain, true);
    Drupal.detachBehaviors(oldMain, drupalSettings, 'unload');
    oldMain.replaceWith(imported);
    Drupal.attachBehaviors(imported, drupalSettings);
    window.scrollTo(0, 0);
    return true;
  }

  function setUp(form) {
    const buttons = [...form.querySelectorAll('input[type="submit"], button[type="submit"], .form-actions a.button')];
    const status = element('div', 'bible-admin-upload-progress', '');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.hidden = true;
    const spinner = element('span', 'bible-admin-spinner');
    spinner.setAttribute('aria-hidden', 'true');
    const words = element('span', 'bible-admin-upload-words');
    status.append(spinner, words);
    (form.querySelector('.form-actions') || form).after(status);
    let isBusy = false;

    function busy(text) {
      isBusy = true;
      status.hidden = false;
      words.textContent = text;
      buttons.forEach((button) => {
        if (button.tagName === 'A') {
          button.setAttribute('aria-disabled', 'true');
          button.classList.add('is-disabled');
        }
        else {
          button.disabled = true;
        }
      });
    }

    function ready(problem = '') {
      isBusy = false;
      words.textContent = problem;
      status.hidden = problem === '';
      status.classList.toggle('is-problem', problem !== '');
      buttons.forEach((button) => {
        button.disabled = false;
        button.removeAttribute('aria-disabled');
        button.classList.remove('is-disabled');
      });
    }

    function hasFile() {
      return [...form.querySelectorAll('input[type="file"]')].some((input) => input.files && input.files.length > 0);
    }

    form.addEventListener('submit', (event) => {
      if (isBusy) {
        event.preventDefault();
        return;
      }
      const sending = hasFile() ? Drupal.t('Uploading…') : Drupal.t('Saving…');
      let data = null;
      try {
        data = new FormData(form, event.submitter);
      }
      catch {
        data = null;
      }
      if (data === null || typeof XMLHttpRequest === 'undefined') {
        // The ordinary submit: the buttons are turned off only after it has started, so the browser still sends
        // the button that was pressed.
        window.setTimeout(() => busy(sending), 0);
        return;
      }
      event.preventDefault();
      busy(sending);
      const request = new XMLHttpRequest();
      request.open('POST', form.getAttribute('action') || window.location.href);
      request.setRequestHeader('X-Bible-Admin-Upload', '1');
      request.upload.onprogress = (progress) => {
        if (progress.lengthComputable && progress.total > 0) {
          const percent = Math.floor((progress.loaded / progress.total) * 100);
          words.textContent = percent < 100
            ? Drupal.t('Uploading… @percent% (keep this page open)', { '@percent': percent })
            : Drupal.t('Saving it… this can take a minute for a large file.');
        }
      };
      request.upload.onload = () => {
        words.textContent = Drupal.t('Saving it… this can take a minute for a large file.');
      };
      request.onload = () => {
        const problem = Drupal.t('The site answered with an error (@status). It may not have been saved: check the list, then try again.', { '@status': request.status });
        if (request.status >= 400 || !request.responseText) {
          ready(problem);
          return;
        }
        if ((request.getResponseHeader('Content-Type') || '').includes('application/json')) {
          let answer = null;
          try {
            answer = JSON.parse(request.responseText);
          }
          catch {
            answer = null;
          }
          if (answer && typeof answer.redirect === 'string') {
            isBusy = false;
            words.textContent = Drupal.t('Saved. Opening the list…');
            window.location.assign(answer.redirect);
            return;
          }
          ready(problem);
          return;
        }
        isBusy = false;
        if (!showMainPart(request.responseText)) {
          ready(problem);
        }
      };
      request.onerror = () => ready(Drupal.t('The connection was lost, so the upload stopped. Try again.'));
      request.onabort = () => ready(Drupal.t('The upload was stopped. Try again.'));
      request.send(data);
    });

    // Leaving the page would stop the upload.
    window.addEventListener('beforeunload', (event) => {
      if (isBusy) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
    // Back to this page from the browser's cache: the form is ready again.
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) {
        ready();
      }
    });
  }

  Drupal.behaviors.bibleAdminUploadProgress = {
    attach(context) {
      once('bible-admin-upload-progress', 'form.bible-admin-upload-progress-form', context).forEach(setUp);
    },
  };
})(Drupal, drupalSettings, once);
