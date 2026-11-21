/**
 * @file
 * Pasting a copied picture into an upload field of the admin forms (2026-11-21, the owner's request: "copy
 * an image and use it for various things in the upload dialog").
 *
 * Every single-file upload field whose accept list takes pictures (the Kindle book picture, the site icons,
 * a map, a song's words picture) gets a "Paste a picture" box under it. Clicking its button reads the
 * clipboard (the browser may ask first); pressing Cmd-V or Ctrl-V while the box has the focus, or anywhere
 * on a page with only one such field (but not while typing in a box or an editor), pastes too. The picture is
 * put in the field as if it had been chosen, with a preview, and is sent when the form is saved, like any
 * upload, so the server checks it as usual. Nothing is kept anywhere else.
 *
 * A picture copied from a web page or a screenshot comes as PNG and is named "pasted-<date>-<time>.png"; a
 * picture file copied in the Finder keeps its own name. The bulk upload box (js/bulk-upload.js) uses
 * Drupal.bibleAdminPaste too.
 */
((Drupal, once) => {
  const EXTENSIONS = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/gif': 'gif', 'image/svg+xml': 'svg', 'image/x-icon': 'ico', 'image/vnd.microsoft.icon': 'ico', 'image/tiff': 'tif' };

  function twoDigits(number) {
    return String(number).padStart(2, '0');
  }

  const namesGiven = new Set();

  // The name a pasted picture without one gets: pasted-2026-11-21-143005.png (pasted-...-143005-2.png for
  // a second one in the same second, so two pasted into the bulk box do not get the same id).
  function pastedName(type) {
    const now = new Date();
    const date = `${now.getFullYear()}-${twoDigits(now.getMonth() + 1)}-${twoDigits(now.getDate())}`;
    const time = `${twoDigits(now.getHours())}${twoDigits(now.getMinutes())}${twoDigits(now.getSeconds())}`;
    let stem = `pasted-${date}-${time}`;
    for (let count = 2; namesGiven.has(stem); count += 1) {
      stem = `pasted-${date}-${time}-${count}`;
    }
    namesGiven.add(stem);
    return `${stem}.${EXTENSIONS[type] || 'png'}`;
  }

  // A File from a blob of the clipboard, keeping the name of a copied file.
  function asFile(blob, name) {
    const hasOwnName = name && name !== 'image.png' && /\.[a-z0-9]+$/i.test(name);
    return new File([blob], hasOwnName ? name : pastedName(blob.type), { type: blob.type, lastModified: Date.now() });
  }

  // The first picture of a paste event, or null.
  function fromPasteEvent(event) {
    const items = [...(event.clipboardData?.items || [])];
    const item = items.find((each) => each.kind === 'file' && each.type.startsWith('image/'));
    const file = item ? item.getAsFile() : null;
    return file ? asFile(file, file.name) : null;
  }

  // Reads a picture from the clipboard with the Clipboard API (a click on Paste). Gives the picture, or a
  // message saying why there is none.
  async function fromClipboard() {
    if (!navigator.clipboard?.read) {
      return { problem: 'This browser cannot read the clipboard from a button: click in this box and press Cmd-V (Ctrl-V on Windows).' };
    }
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((each) => each.startsWith('image/'));
        if (type) {
          return { file: asFile(await item.getType(type), '') };
        }
      }
      return { problem: 'There is no picture on the clipboard. Copy one first (for example right-click a picture and choose Copy Image).' };
    }
    catch (error) {
      return { problem: 'The browser did not let the page read the clipboard. Click in this box and press Cmd-V (Ctrl-V on Windows) instead.' };
    }
  }

  // Whether a file input takes pictures (its accept list names a picture type or extension).
  function takesPictures(input) {
    const accept = (input.getAttribute('accept') || '').toLowerCase();
    return /image\/|\.png|\.jpe?g|\.webp|\.gif/.test(accept);
  }

  // Whether the field's accept list allows this file (by its type or its extension).
  function isAccepted(input, file) {
    const accept = (input.getAttribute('accept') || '').toLowerCase().split(',').map((each) => each.trim()).filter(Boolean);
    if (accept.length === 0) {
      return true;
    }
    const extension = `.${(file.name.split('.').pop() || '').toLowerCase()}`;
    return accept.some((each) => each === file.type || each === extension || (each === '.jpg' && extension === '.jpeg') || (each.endsWith('/*') && file.type.startsWith(each.slice(0, -1))));
  }

  function megabytes(bytes) {
    return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  // Whether the focus is in something one types into (a paste there is text, not for us).
  function isTyping(target) {
    return target instanceof HTMLElement && (target.isContentEditable || target.matches('input:not([type=file]):not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]), textarea, select'));
  }

  const boxes = [];

  function setUp(input) {
    const box = document.createElement('div');
    box.className = 'bible-admin-paste';
    box.tabIndex = 0;
    box.setAttribute('aria-label', 'Paste a picture into this upload field');
    const row = document.createElement('div');
    row.className = 'bible-admin-paste-row';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button button--small';
    button.textContent = 'Paste a picture';
    const hint = document.createElement('span');
    hint.className = 'bible-admin-paste-hint';
    hint.textContent = 'or click here and press Cmd-V (Ctrl-V on Windows) to use a picture you copied';
    row.append(button, hint);
    const preview = document.createElement('div');
    preview.className = 'bible-admin-paste-preview';
    preview.hidden = true;
    const image = document.createElement('img');
    image.alt = 'The pasted picture';
    const about = document.createElement('span');
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'button button--small';
    clear.textContent = 'Clear';
    preview.append(image, about, clear);
    const message = document.createElement('div');
    message.className = 'bible-admin-paste-message';
    message.setAttribute('aria-live', 'polite');
    box.append(row, preview, message);
    input.insertAdjacentElement('afterend', box);
    let pictureAddress = '';

    function showPreview(file) {
      if (pictureAddress) {
        URL.revokeObjectURL(pictureAddress);
        pictureAddress = '';
      }
      if (!file) {
        preview.hidden = true;
        image.removeAttribute('src');
        return;
      }
      pictureAddress = URL.createObjectURL(file);
      image.src = pictureAddress;
      about.textContent = `${file.name} (${megabytes(file.size)}) will be uploaded when you save.`;
      preview.hidden = false;
    }

    function use(file) {
      message.textContent = '';
      if (!isAccepted(input, file)) {
        message.textContent = `This field does not take ${file.type || 'that kind of file'}.`;
        return;
      }
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      showPreview(file);
    }

    // A file chosen the ordinary way replaces the pasted one, so the preview goes.
    input.addEventListener('change', (event) => {
      if (event.isTrusted) {
        showPreview(null);
        message.textContent = '';
      }
    });
    button.addEventListener('click', async () => {
      message.textContent = 'Reading the clipboard…';
      const { file, problem } = await fromClipboard();
      message.textContent = problem || '';
      if (file) {
        use(file);
      }
    });
    clear.addEventListener('click', () => {
      input.value = '';
      showPreview(null);
      message.textContent = '';
    });
    box.addEventListener('paste', (event) => {
      const file = fromPasteEvent(event);
      event.preventDefault();
      event.stopPropagation();
      if (file) {
        use(file);
      }
      else {
        message.textContent = 'There is no picture on the clipboard.';
      }
    });
    boxes.push({ input, use });
  }

  // A paste anywhere else on a page with only one picture field goes into it.
  document.addEventListener('paste', (event) => {
    if (boxes.length !== 1 || isTyping(event.target) || !document.contains(boxes[0].input)) {
      return;
    }
    const file = fromPasteEvent(event);
    if (file) {
      event.preventDefault();
      boxes[0].use(file);
    }
  });

  Drupal.bibleAdminPaste = { fromPasteEvent, fromClipboard, isTyping };

  Drupal.behaviors.bibleAdminPastePicture = {
    attach(context) {
      once('bible-admin-paste', 'input[type=file]:not([multiple])', context)
        .filter(takesPictures)
        .forEach(setUp);
    },
  };
})(Drupal, once);
