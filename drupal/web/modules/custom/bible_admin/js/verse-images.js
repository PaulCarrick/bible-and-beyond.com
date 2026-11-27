/**
 * @file
 * The verse a day pictures list (VerseImageListController):
 *
 * - A pencil after each name changes it in place: the name becomes a text box with Save and Cancel (Enter saves,
 *   Escape cancels). It is saved with a POST to the row's data-rename-url, with the CSRF header.
 * - A click on a thumbnail opens the picture larger in a window over the page, with its name and a close button
 *   (Escape, the close button or a click outside closes it, and the focus goes back to the thumbnail). The larger
 *   copy is fetched from the row's data-preview-url when the window opens; the pictures are never public.
 */
(function (Drupal, once) {
  'use strict';

  let tokenPromise = null;
  function csrfToken(tokenUrl) {
    if (!tokenPromise) {
      tokenPromise = fetch(tokenUrl, { credentials: 'same-origin' }).then((response) => response.text());
    }
    return tokenPromise;
  }

  async function answerOf(response) {
    try {
      return await response.json();
    }
    catch (error) {
      return { ok: false, error: Drupal.t('The server did not answer as expected (@status).', { '@status': response.status }) };
    }
  }

  function setUpRename(cell, tokenUrl) {
    const box = cell.querySelector('.verse-image-name');
    const title = box.querySelector('.verse-image-title');
    const pencil = document.createElement('button');
    pencil.type = 'button';
    pencil.className = 'verse-image-pencil';
    pencil.textContent = '✎';
    pencil.title = Drupal.t('Change the name');
    pencil.setAttribute('aria-label', Drupal.t('Change the name “@title”', { '@title': title.textContent }));
    title.after(pencil);

    pencil.addEventListener('click', () => {
      const old = title.textContent;
      const editor = document.createElement('span');
      editor.className = 'verse-image-editor';
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'form-text form-element form-element--type-text';
      input.value = old;
      input.maxLength = 200;
      input.setAttribute('aria-label', Drupal.t('Name'));
      const save = document.createElement('button');
      save.type = 'button';
      save.className = 'button button--small button--primary';
      save.textContent = Drupal.t('Save');
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'button button--small';
      cancel.textContent = Drupal.t('Cancel');
      const message = document.createElement('span');
      message.className = 'verse-image-rename-message';
      message.setAttribute('role', 'alert');
      editor.append(input, save, cancel, message);

      title.hidden = true;
      pencil.hidden = true;
      title.after(editor);
      input.focus();
      input.select();

      function close(newTitle) {
        if (newTitle !== undefined) {
          title.textContent = newTitle;
          cell.setAttribute('data-sort-value', newTitle);
          pencil.setAttribute('aria-label', Drupal.t('Change the name “@title”', { '@title': newTitle }));
        }
        editor.remove();
        title.hidden = false;
        pencil.hidden = false;
        pencil.focus();
      }

      async function send() {
        const typed = input.value.trim();
        if (!typed) {
          message.textContent = Drupal.t('Type a name.');
          input.focus();
          return;
        }
        if (typed === old) {
          close();
          return;
        }
        save.disabled = cancel.disabled = input.disabled = true;
        message.textContent = Drupal.t('Saving…');
        try {
          const token = await csrfToken(tokenUrl);
          const response = await fetch(box.dataset.renameUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRF-Token': token },
            body: new URLSearchParams({ title: typed }),
          });
          const answer = await answerOf(response);
          if (answer.ok) {
            close(answer.title);
            return;
          }
          message.textContent = answer.error || Drupal.t('The name could not be saved.');
        }
        catch (error) {
          message.textContent = Drupal.t('The name could not be saved (no connection).');
        }
        save.disabled = cancel.disabled = input.disabled = false;
        input.focus();
      }

      save.addEventListener('click', send);
      cancel.addEventListener('click', () => close());
      input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          send();
        }
        else if (event.key === 'Escape') {
          event.preventDefault();
          close();
        }
      });
    });
  }

  function openWindow(button) {
    const backdrop = document.createElement('div');
    backdrop.className = 'verse-image-window-backdrop';
    const panel = document.createElement('div');
    panel.className = 'verse-image-window';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', 'verse-image-window-title');
    const header = document.createElement('div');
    header.className = 'verse-image-window-header';
    const heading = document.createElement('h2');
    heading.id = 'verse-image-window-title';
    const row = button.closest('tr');
    heading.textContent = row?.querySelector('.verse-image-title')?.textContent || Drupal.t('Picture');
    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'verse-image-window-close';
    closeButton.textContent = '×';
    closeButton.setAttribute('aria-label', Drupal.t('Close'));
    header.append(heading, closeButton);
    const body = document.createElement('div');
    body.className = 'verse-image-window-body';
    body.textContent = Drupal.t('Loading…');
    const foot = document.createElement('p');
    foot.className = 'verse-image-window-foot';
    panel.append(header, body, foot);
    backdrop.append(panel);
    document.body.append(backdrop);
    document.body.classList.add('verse-image-window-open');
    closeButton.focus();

    function close() {
      document.removeEventListener('keydown', onKey);
      backdrop.remove();
      document.body.classList.remove('verse-image-window-open');
      button.focus();
    }
    function onKey(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
      }
      else if (event.key === 'Tab') {
        // Only the close button can take the focus in the window.
        event.preventDefault();
        closeButton.focus();
      }
    }
    document.addEventListener('keydown', onKey);
    closeButton.addEventListener('click', close);
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) {
        close();
      }
    });

    fetch(button.dataset.previewUrl, { credentials: 'same-origin' })
      .then(answerOf)
      .then((answer) => {
        if (!backdrop.isConnected) {
          return;
        }
        if (!answer.ok) {
          body.textContent = answer.error || Drupal.t('The picture could not be shown.');
          return;
        }
        const image = document.createElement('img');
        image.src = answer.preview;
        image.alt = answer.title;
        body.textContent = '';
        body.append(image);
        heading.textContent = answer.title;
        foot.textContent = Drupal.t('@width × @height pixels (shown smaller here)', { '@width': answer.width, '@height': answer.height });
      })
      .catch(() => {
        if (backdrop.isConnected) {
          body.textContent = Drupal.t('The picture could not be shown (no connection).');
        }
      });
  }

  Drupal.behaviors.bibleAdminVerseImages = {
    attach(context) {
      once('verse-images', 'table.verse-images-table', context).forEach((table) => {
        const tokenUrl = table.dataset.tokenUrl;
        table.querySelectorAll('td[data-sort-value]').forEach((cell) => {
          if (cell.querySelector('.verse-image-name')) {
            setUpRename(cell, tokenUrl);
          }
        });
        table.addEventListener('click', (event) => {
          const button = event.target.closest('.verse-image-enlarge');
          if (button) {
            openWindow(button);
          }
        });
      });
    },
  };
})(Drupal, once);
