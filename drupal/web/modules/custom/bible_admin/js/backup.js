/**
 * The Backup and restore page (BackupController). Backing up: pick a folder on this computer (Chrome and
 * Edge; other browsers download the zip instead), have the server build the zip, save it into the folder,
 * then have the server delete its copy. Restoring: pick a backup zip, upload it a part at a time, then have
 * the server restore it, showing its progress until it is done (or until restoring Drupal's database logs
 * the administrator out).
 */
((Drupal, drupalSettings, once) => {
  const settings = drupalSettings.bibleAdminBackup;
  const POLL_MILLISECONDS = 2000;
  const PICKER_ID = 'bible-and-beyond-backups';

  Drupal.behaviors.bibleAdminBackup = {
    attach(context) {
      once('bible-backup', '.bible-backup', context).forEach(setUp);
    },
  };

  function setUp(page) {
    const find = (name) => page.querySelector(`[data-backup="${name}"]`);
    const statusBox = page.querySelector('.bible-backup__status');
    const progress = find('progress');
    const buttons = [find('start'), find('choose'), find('restore')];
    let token = null;
    let chosenFile = null;
    let busy = false;

    if (!window.showDirectoryPicker) {
      find('no-folder-hint').hidden = false;
    }

    const parts = () => ({
      database: page.querySelector('#backup-database').checked,
      files: page.querySelector('#backup-files').checked,
    });

    function setBusy(isBusy) {
      busy = isBusy;
      buttons.forEach((button) => { button.disabled = isBusy; });
    }

    function show(text, kind = 'status', actions = []) {
      statusBox.innerHTML = '';
      if (!text) {
        return;
      }
      const box = document.createElement('div');
      box.className = `messages messages--${kind}`;
      const paragraph = document.createElement('p');
      paragraph.textContent = text;
      box.append(paragraph);
      actions.forEach(([label, handler]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'button button--small';
        button.textContent = label;
        button.addEventListener('click', handler);
        box.append(button, ' ');
      });
      statusBox.append(box);
    }

    function showProgress(fraction, text) {
      progress.hidden = fraction === null;
      if (fraction !== null) {
        progress.querySelector('progress').value = Math.round(fraction * 100);
        progress.querySelector('span').textContent = text;
      }
    }

    function size(bytes) {
      if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
      if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
      return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }

    // A JSON request to the page's routes. A 403 or a login page means the session is gone (restoring
    // Drupal's database logs everyone out).
    async function call(url, options = {}) {
      const response = await fetch(url, { credentials: 'same-origin', ...options });
      if (response.status === 403) {
        const error = new Error('logged out');
        error.loggedOut = true;
        throw error;
      }
      let answer;
      try {
        answer = await response.json();
      }
      catch {
        const error = new Error(Drupal.t('The server gave an unexpected answer.'));
        error.loggedOut = response.redirected;
        throw error;
      }
      if (!answer.ok) {
        throw new Error(answer.error || Drupal.t('Something went wrong.'));
      }
      return answer;
    }

    async function post(action, body, query = '') {
      if (!token) {
        token = await (await fetch(settings.tokenUrl, { credentials: 'same-origin' })).text();
      }
      const isBlob = body instanceof Blob;
      return call(`${settings.pageUrl}/${action}${query}`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': token, 'Content-Type': isBlob ? 'application/octet-stream' : 'application/json' },
        body: isBlob ? body : JSON.stringify(body || {}),
      });
    }

    const wait = (milliseconds) => new Promise((resolve) => { setTimeout(resolve, milliseconds); });

    // Asks the server how the job is going until it finishes; returns the last answer.
    async function follow(action) {
      for (;;) {
        const answer = await call(settings.statusUrl);
        const status = answer.status;
        if (!status || status.action !== action || !['starting', 'running'].includes(status.state)) {
          return answer;
        }
        show(status.message, 'warning');
        await wait(POLL_MILLISECONDS);
      }
    }

    function loggedOutMessage() {
      show(
        Drupal.t('Drupal\'s database has been replaced, so you are logged out. Log in again, with an account and password from the backup, and come back to this page to see how the restore ended.'),
        'warning',
        [[Drupal.t('Log in'), () => { window.location.href = settings.loginUrl; }]],
      );
    }

    // Saves the zip waiting on the server into the folder (or downloads it), then deletes it on the server.
    async function save(waiting, folder) {
      const url = `${settings.pageUrl}/download/${encodeURIComponent(waiting.name)}`;
      if (!folder) {
        const link = document.createElement('a');
        link.href = url;
        link.download = waiting.name;
        document.body.append(link);
        link.click();
        link.remove();
        show(
          Drupal.t('@name (@size) is being downloaded. Once it has finished, delete the copy on the server.', { '@name': waiting.name, '@size': size(waiting.size) }),
          'status',
          [[Drupal.t('Delete the copy on the server'), discard]],
        );
        return;
      }
      const response = await fetch(url, { credentials: 'same-origin' });
      if (!response.ok) {
        throw new Error(Drupal.t('The backup could not be fetched from the server.'));
      }
      const handle = await folder.getFileHandle(waiting.name, { create: true });
      const writable = await handle.createWritable();
      const reader = response.body.getReader();
      let received = 0;
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          await writable.write(value);
          received += value.length;
          showProgress(received / waiting.size, Drupal.t('Saving: @done of @total', { '@done': size(received), '@total': size(waiting.size) }));
        }
        await writable.close();
      }
      catch (error) {
        await writable.abort().catch(() => {});
        throw error;
      }
      if (received !== waiting.size) {
        throw new Error(Drupal.t('Only part of the backup arrived; try again.'));
      }
      await post('discard');
      showProgress(null);
      show(Drupal.t('Saved @name (@size) in the folder "@folder".', { '@name': waiting.name, '@size': size(waiting.size), '@folder': folder.name }));
    }

    async function discard() {
      try {
        await post('discard');
        show(Drupal.t('The copy on the server has been deleted.'));
      }
      catch (error) {
        show(error.message, 'error');
      }
    }

    async function backUp() {
      const chosen = parts();
      if (!chosen.database && !chosen.files) {
        show(Drupal.t('Tick Database, Files or both.'), 'error');
        return;
      }
      let folder = null;
      if (window.showDirectoryPicker) {
        try {
          folder = await window.showDirectoryPicker({ id: PICKER_ID, mode: 'readwrite' });
        }
        catch {
          return; // The folder picker was cancelled.
        }
      }
      setBusy(true);
      try {
        await post('start', { ...chosen, note: page.querySelector('#backup-note').value });
        show(Drupal.t('Building the backup ...'), 'warning');
        const answer = await follow('backup');
        if (answer.status && answer.status.state === 'failed') {
          throw new Error(Drupal.t('The backup failed: @message', { '@message': answer.status.message }));
        }
        if (!answer.waiting) {
          throw new Error(Drupal.t('The backup did not arrive on the server.'));
        }
        await save(answer.waiting, folder);
      }
      catch (error) {
        showProgress(null);
        show(error.message, 'error');
      }
      finally {
        setBusy(false);
      }
    }

    function choose(file) {
      chosenFile = file;
      find('chosen').textContent = Drupal.t('Chosen: @name (@size)', { '@name': file.name, '@size': size(file.size) });
      find('restore-panel').hidden = false;
      page.querySelector('#backup-confirm').focus();
    }

    async function pickFile() {
      if (window.showOpenFilePicker) {
        try {
          const [handle] = await window.showOpenFilePicker({
            id: PICKER_ID,
            types: [{ description: Drupal.t('Backup zip'), accept: { 'application/zip': ['.zip'] } }],
          });
          choose(await handle.getFile());
        }
        catch {
          // The picker was cancelled.
        }
        return;
      }
      find('file').click();
    }

    async function restore() {
      const chosen = parts();
      if (!chosen.database && !chosen.files) {
        show(Drupal.t('Tick Database, Files or both.'), 'error');
        return;
      }
      if (page.querySelector('#backup-confirm').value.trim() !== 'RESTORE') {
        show(Drupal.t('Type RESTORE in capitals to confirm.'), 'error');
        return;
      }
      setBusy(true);
      try {
        const file = chosenFile;
        for (let offset = 0; offset < file.size || offset === 0; offset += settings.chunkBytes) {
          await post('upload', file.slice(offset, offset + settings.chunkBytes), `?offset=${offset}`);
          const sent = Math.min(file.size, offset + settings.chunkBytes);
          showProgress(sent / file.size, Drupal.t('Uploading: @done of @total', { '@done': size(sent), '@total': size(file.size) }));
          if (file.size === 0) break;
        }
        showProgress(null);
        await post('restore', { ...chosen, size: file.size });
        show(Drupal.t('Restoring ...'), 'warning');
        const answer = await follow('restore');
        page.querySelector('#backup-confirm').value = '';
        find('restore-panel').hidden = true;
        finished(answer.status);
      }
      catch (error) {
        showProgress(null);
        if (error.loggedOut) {
          loggedOutMessage();
        }
        else {
          show(error.message, 'error');
        }
      }
      finally {
        setBusy(false);
      }
    }

    // A finished job: its message, with Dismiss.
    function finished(status) {
      if (!status) return;
      const failed = status.state === 'failed';
      const text = status.action === 'backup'
        ? (failed ? Drupal.t('The last backup failed: @message', { '@message': status.message }) : status.message)
        : (failed ? Drupal.t('The restore failed: @message', { '@message': status.message }) : status.message);
      show(text, failed ? 'error' : 'status', [[Drupal.t('Dismiss'), async () => {
        await post('dismiss').catch(() => {});
        show('');
      }]]);
    }

    find('start').addEventListener('click', () => { if (!busy) backUp(); });
    find('choose').addEventListener('click', () => { if (!busy) pickFile(); });
    find('file').addEventListener('change', (event) => { if (event.target.files[0]) choose(event.target.files[0]); });
    find('restore').addEventListener('click', () => { if (!busy && chosenFile) restore(); });

    // What the server is doing now: a job still running (started from another tab, or before a reload), a
    // finished one, or a backup waiting to be saved.
    (async () => {
      try {
        let answer = await call(settings.statusUrl);
        if (answer.status && ['starting', 'running'].includes(answer.status.state)) {
          setBusy(true);
          answer = await follow(answer.status.action);
          setBusy(false);
        }
        if (answer.waiting) {
          show(
            Drupal.t('A backup is waiting on the server: @name (@size).', { '@name': answer.waiting.name, '@size': size(answer.waiting.size) }),
            'warning',
            [
              [Drupal.t('Save it to a folder…'), async () => {
                let folder = null;
                if (window.showDirectoryPicker) {
                  try {
                    folder = await window.showDirectoryPicker({ id: PICKER_ID, mode: 'readwrite' });
                  }
                  catch {
                    return;
                  }
                }
                setBusy(true);
                try {
                  await save(answer.waiting, folder);
                }
                catch (error) {
                  showProgress(null);
                  show(error.message, 'error');
                }
                finally {
                  setBusy(false);
                }
              }],
              [Drupal.t('Delete it from the server'), discard],
            ],
          );
        }
        else {
          finished(answer.status);
        }
      }
      catch (error) {
        setBusy(false);
        if (error.loggedOut) {
          loggedOutMessage();
        }
        else {
          show(error.message, 'error');
        }
      }
    })();
  }
})(Drupal, drupalSettings, once);
