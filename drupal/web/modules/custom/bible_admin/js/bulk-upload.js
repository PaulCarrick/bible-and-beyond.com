/**
 * @file
 * Uploading several files at once on the Christian music, Devotionals and Other books pages, like the media
 * library of the Jump Start Website: drop files on the area (or choose them), fill in what applies to all of
 * them, and press Upload. The files are sent one at a time to bible_admin.bulk_upload (a song can be 1 GB, so
 * they never share one request), each with its own line: waiting, sending (with how much), reading, and then
 * what became of it. Each becomes a new item named after its file; one whose id is in use is skipped.
 *
 * The inputs are made here, not by Drupal, so no form is nested in the page; the area's data attributes say
 * which page it is (BulkUploadController::area).
 */
((Drupal, once) => {
  function element(tag, properties = {}, children = []) {
    const made = document.createElement(tag);
    Object.entries(properties).forEach(([name, value]) => {
      if (name === 'text') {
        made.textContent = value;
      }
      else if (name in made && name !== 'list') {
        made[name] = value;
      }
      else {
        made.setAttribute(name, value);
      }
    });
    children.forEach((child) => made.append(child));
    return made;
  }

  function megabytes(bytes) {
    return `${(bytes / 1048576).toFixed(bytes < 10485760 ? 1 : 0)} MB`;
  }

  function field(label, input, description) {
    const wrapper = element('div', { className: 'bible-admin-bulk-field' }, [element('label', { text: label, htmlFor: input.id }), input]);
    if (description) {
      wrapper.append(element('div', { className: 'bible-admin-bulk-hint', text: description }));
    }
    return wrapper;
  }

  function checkbox(id, label) {
    const input = element('input', { type: 'checkbox', id });
    return { input, wrapper: element('div', { className: 'bible-admin-bulk-check' }, [input, element('label', { htmlFor: id, text: label })]) };
  }

  function setUp(area) {
    const { collection, uploadUrl, tokenUrl, one, many } = area.dataset;
    const extensions = area.dataset.extensions.split(',');
    const maxFiles = Number(area.dataset.maxFiles);
    const maxBytes = Number(area.dataset.maxBytes);
    const isMusic = collection === 'music';
    const prefix = `bulk-${collection}`;
    let chosen = [];
    let isBusy = false;

    const input = element('input', { type: 'file', id: `${prefix}-files`, multiple: true, className: 'visually-hidden', accept: extensions.map((each) => `.${each}`).join(',') });
    const chosenNote = element('div', { className: 'bible-admin-bulk-chosen', 'aria-live': 'polite' });
    const zone = element('div', { className: 'bible-admin-bulk-zone' }, [
      element('strong', { text: `Drop ${one} files here` }),
      element('span', {}, [
        'or ',
        element('label', { htmlFor: input.id, className: 'bible-admin-bulk-choose', text: 'choose files' }),
        ` (${extensions.map((each) => `.${each}`).join(', ')}), up to ${maxFiles} at a time. Each becomes a new ${one} named after its file; one already there is left as it is.`,
      ]),
      chosenNote,
      input,
    ]);

    const options = element('div', { className: 'bible-admin-bulk-options' });
    const inputs = {};
    if (!isMusic) {
      inputs.author = element('input', { type: 'text', id: `${prefix}-author`, maxLength: 200 });
      inputs.source = element('input', { type: 'text', id: `${prefix}-source`, maxLength: 200 });
      inputs.keywords = element('input', { type: 'text', id: `${prefix}-keywords`, maxLength: 500 });
      options.append(
        field('Author (for all of them)', inputs.author),
        field('Where the texts came from (for all of them)', inputs.source, 'Shown in the credit on the site.'),
      );
      if (collection === 'devotionals') {
        inputs.kind = element('select', { id: `${prefix}-kind` }, [
          element('option', { value: 'chapters', text: 'By chapter: parts and chapters, read in order' }),
          element('option', { value: 'daily', text: 'Daily: a reading for each day of the year' }),
        ]);
        options.append(field('Kind', inputs.kind));
      }
      options.append(field('Keywords (for all of them, optional)', inputs.keywords, 'Words or phrases, separated by commas, that the searches also find them by.'));
      const whole = checkbox(`${prefix}-whole`, 'Keep each PDF, Word document or ebook as one chapter (not cut at its headings)');
      inputs.whole = whole.input;
      options.append(whole.wrapper);
    }
    const publish = checkbox(`${prefix}-publish`, `Publish them when uploaded (otherwise each new ${one} is hidden until you publish it)`);
    inputs.publish = publish.input;
    options.append(publish.wrapper);

    const uploadButton = element('button', { type: 'button', className: 'button button--primary', text: 'Upload', disabled: true });
    const clearButton = element('button', { type: 'button', className: 'button', text: 'Clear', disabled: true });
    const listButton = element('button', { type: 'button', className: 'button', text: `Show them in the list of ${many}`, hidden: true });
    const message = element('div', { className: 'bible-admin-bulk-message', 'aria-live': 'polite' });
    const list = element('ol', { className: 'bible-admin-bulk-list' });

    area.append(
      element('h2', { text: `Upload several ${many} at once` }),
      zone,
      options,
      element('div', { className: 'bible-admin-bulk-actions' }, [uploadButton, clearButton, listButton]),
      message,
      list,
    );

    function show(files) {
      chosen = [];
      list.replaceChildren();
      message.textContent = '';
      listButton.hidden = true;
      [...files].forEach((file, index) => {
        const extension = (file.name.split('.').pop() || '').toLowerCase();
        let problem = '';
        if (index >= maxFiles) {
          problem = `Not sent: at most ${maxFiles} files at a time.`;
        }
        else if (!extensions.includes(extension)) {
          problem = `Not sent: not a file this page takes.`;
        }
        else if (file.size > maxBytes) {
          problem = `Not sent: larger than ${megabytes(maxBytes)}.`;
        }
        const status = element('span', { className: 'bible-admin-bulk-status', text: problem || 'Waiting' });
        const row = element('li', { className: problem ? 'is-skipped' : '' }, [
          element('span', { className: 'bible-admin-bulk-name', text: file.name }),
          element('span', { className: 'bible-admin-bulk-size', text: megabytes(file.size) }),
          status,
        ]);
        list.append(row);
        if (!problem) {
          chosen.push({ file, row, status });
        }
      });
      chosenNote.textContent = chosen.length ? `${chosen.length} ${chosen.length === 1 ? 'file' : 'files'} ready.` : '';
      uploadButton.disabled = chosen.length === 0;
      clearButton.disabled = files.length === 0;
    }

    function sendOne(item, token) {
      return new Promise((resolve) => {
        const data = new FormData();
        data.append('file', item.file);
        data.append('publish', inputs.publish.checked ? '1' : '0');
        if (!isMusic) {
          data.append('author', inputs.author.value);
          data.append('source_name', inputs.source.value);
          data.append('keywords', inputs.keywords.value);
          data.append('whole', inputs.whole.checked ? '1' : '0');
          if (inputs.kind) {
            data.append('devotional_kind', inputs.kind.value);
          }
        }
        const request = new XMLHttpRequest();
        request.open('POST', uploadUrl);
        request.setRequestHeader('X-CSRF-Token', token);
        request.upload.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            item.status.textContent = percent < 100 ? `Sending… ${percent}%` : 'Reading it…';
          }
        };
        request.onload = () => {
          let answer = null;
          try {
            answer = JSON.parse(request.responseText);
          }
          catch {
            answer = { ok: false, error: `The server answered ${request.status}.` };
          }
          resolve(answer);
        };
        request.onerror = () => resolve({ ok: false, error: 'The connection was lost.' });
        request.send(data);
      });
    }

    async function uploadAll() {
      if (!isMusic && (!inputs.author.value.trim() || !inputs.source.value.trim())) {
        message.textContent = 'Fill in the author and where the texts came from first.';
        (inputs.author.value.trim() ? inputs.source : inputs.author).focus();
        return;
      }
      isBusy = true;
      uploadButton.disabled = true;
      clearButton.disabled = true;
      input.disabled = true;
      message.textContent = 'Uploading… keep this page open until every file is done.';
      let token;
      try {
        token = await (await fetch(tokenUrl, { credentials: 'same-origin' })).text();
      }
      catch {
        message.textContent = 'The upload could not start (no answer from the site). Try again.';
        isBusy = false;
        uploadButton.disabled = false;
        clearButton.disabled = false;
        input.disabled = false;
        return;
      }
      const counts = { uploaded: 0, skipped: 0, failed: 0 };
      for (const item of chosen) {
        item.status.textContent = 'Sending…';
        const answer = await sendOne(item, token);
        if (answer.ok) {
          counts.uploaded += 1;
          item.row.className = 'is-done';
          item.status.textContent = `Uploaded as “${answer.name}” (${answer.id})${answer.published ? ', published' : ', hidden'}`;
        }
        else if (answer.skipped) {
          counts.skipped += 1;
          item.row.className = 'is-skipped';
          item.status.textContent = `Skipped: ${answer.skipped}`;
        }
        else {
          counts.failed += 1;
          item.row.className = 'is-failed';
          item.status.textContent = `Not uploaded: ${answer.error}`;
        }
      }
      isBusy = false;
      input.disabled = false;
      clearButton.disabled = false;
      chosen = [];
      chosenNote.textContent = '';
      message.textContent = `Done: ${counts.uploaded} uploaded, ${counts.skipped} skipped, ${counts.failed} not uploaded.`;
      listButton.hidden = counts.uploaded === 0;
    }

    input.addEventListener('change', () => show(input.files));
    zone.addEventListener('dragover', (event) => {
      if (isBusy || !event.dataTransfer?.types?.includes('Files')) {
        return;
      }
      event.preventDefault();
      zone.classList.add('is-over');
    });
    zone.addEventListener('dragleave', (event) => {
      if (!zone.contains(event.relatedTarget)) {
        zone.classList.remove('is-over');
      }
    });
    zone.addEventListener('drop', (event) => {
      if (isBusy || !event.dataTransfer?.files?.length) {
        return;
      }
      event.preventDefault();
      zone.classList.remove('is-over');
      show(event.dataTransfer.files);
    });
    uploadButton.addEventListener('click', uploadAll);
    clearButton.addEventListener('click', () => {
      input.value = '';
      show([]);
    });
    listButton.addEventListener('click', () => window.location.reload());
    // Leaving the page would stop the files not yet sent.
    window.addEventListener('beforeunload', (event) => {
      if (isBusy) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
  }

  Drupal.behaviors.bibleAdminBulkUpload = {
    attach(context) {
      once('bible-admin-bulk-upload', '.bible-admin-bulk-upload', context).forEach(setUp);
    },
  };
})(Drupal, once);
