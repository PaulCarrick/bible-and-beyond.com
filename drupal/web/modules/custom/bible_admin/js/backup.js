/**
 * The Backup and restore page (BackupController). Backing up: pick a folder on this computer (Chrome and
 * Edge; other browsers download the zips instead), have the server build the backup (up to three zips: the
 * Bible database, Drupal's database, the files), save each zip into the folder and have the server delete
 * that zip once it is saved. A zip that could not be saved (a network error, say) stays on the server and is
 * offered again, here and whenever the page is opened, until it is saved, deleted or a new backup is started.
 * Restoring: pick one or more zips of one backup, upload each a part at a time, then have the server restore
 * them, showing its progress until it is done (or until restoring Drupal's database logs the administrator
 * out).
 */
((Drupal, drupalSettings, once) => {
  const settings = drupalSettings.bibleAdminBackup;
  const POLL_MILLISECONDS = 2000;
  const PICKER_ID = 'bible-and-beyond-backups';
  // A zip's name: the backup's stem, then its part (none for a zip made before backups were split, 2026-11-21).
  const NAME_PATTERN = /^(bible-and-beyond-\d{4}-\d{2}-\d{2}-\d{6})(?:-(bible-database|drupal-database|files))?\.zip$/;

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
    let chosenFiles = [];
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
      (Array.isArray(text) ? text : [text]).forEach((line) => {
        const paragraph = document.createElement('p');
        paragraph.textContent = line;
        box.append(paragraph);
      });
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

    const pickFolder = async () => {
      if (!window.showDirectoryPicker) {
        return null;
      }
      return window.showDirectoryPicker({ id: PICKER_ID, mode: 'readwrite' });
    };

    const describe = (files) => files.map((file) => `${file.name} (${size(file.size)})`).join(', ');

    // Saves the zips waiting on the server into the folder, one after another, and has the server delete each
    // one as soon as it is saved. One that fails (a network error, say) is left on the server, the others still
    // go, and the page then offers the ones left. Chrome counts a file written into a folder against the
    // storage it allows this site, not the free disk, so a big zip can be refused there ("QuotaExceededError";
    // met on 2026-11-17 with 50 GB free): that one is downloaded the ordinary way instead (and kept on the
    // server until it is deleted, since the page cannot tell when a download has finished). With no folder
    // (other browsers), every zip is downloaded that way.
    async function saveAll(waiting, folder) {
      if (!folder) {
        await downloadAll(waiting, '');
        return;
      }
      const saved = [];
      const failed = [];
      const downloaded = [];
      let quota = false;
      for (const [index, file] of waiting.entries()) {
        const url = `${settings.pageUrl}/download/${encodeURIComponent(file.name)}`;
        try {
          await saveToFolder(file, folder, url, `${index + 1}/${waiting.length}`);
          await post('discard', { name: file.name });
          saved.push(file);
        }
        catch (error) {
          await folder.removeEntry(file.name).catch(() => {});
          if (error && error.name === 'QuotaExceededError') {
            quota = true;
            startDownload(file, url);
            downloaded.push(file);
            await wait(1000);
          }
          else {
            failed.push({ ...file, reason: error && error.message ? error.message : String(error) });
          }
        }
      }
      showProgress(null);
      const lines = [];
      if (saved.length) {
        lines.push(Drupal.t('Saved in the folder "@folder" and deleted from the server: @files.', { '@folder': folder.name, '@files': describe(saved) }));
      }
      if (downloaded.length) {
        lines.push(Drupal.t('Chrome would not save @files into that folder: bigger than the storage Chrome allows this site (this has nothing to do with your free disk space). Downloaded instead; once that has finished, delete the copy on the server.', { '@files': describe(downloaded) }));
      }
      failed.forEach((file) => {
        lines.push(Drupal.t('@name could not be saved (@reason). It is still on the server: save it again.', { '@name': file.name, '@reason': file.reason }));
      });
      if (!failed.length && !downloaded.length) {
        show(lines);
        return;
      }
      offerWaiting(await waitingNow(), lines, failed.length ? 'error' : 'warning', quota);
    }

    // The zips the server still holds.
    async function waitingNow() {
      return (await call(settings.statusUrl)).waiting || [];
    }

    // The ordinary browser download (to the Downloads folder), one zip after another; the copies on the server
    // stay until they are deleted.
    async function downloadAll(waiting, reason) {
      for (const file of waiting) {
        startDownload(file, `${settings.pageUrl}/download/${encodeURIComponent(file.name)}`);
        await wait(1000); // Some browsers drop downloads started at the same moment.
      }
      show(
        [reason + Drupal.t('Being downloaded: @files.', { '@files': describe(waiting) }),
          Drupal.t('Once they have finished, delete the copies on the server. If one did not arrive, download it again from the message shown when this page is opened.')],
        'status',
        [[Drupal.t('Delete the copies on the server'), discardAll]],
      );
    }

    function startDownload(file, url) {
      const link = document.createElement('a');
      link.href = url;
      link.download = file.name;
      document.body.append(link);
      link.click();
      link.remove();
    }

    async function saveToFolder(file, folder, url, counter) {
      const response = await fetch(url, { credentials: 'same-origin' });
      if (!response.ok) {
        throw new Error(Drupal.t('the server did not send it'));
      }
      const handle = await folder.getFileHandle(file.name, { create: true });
      const writable = await handle.createWritable();
      const reader = response.body.getReader();
      let received = 0;
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          await writable.write(value);
          received += value.length;
          showProgress(received / file.size, Drupal.t('Saving @counter, @name: @done of @total', { '@counter': counter, '@name': file.name, '@done': size(received), '@total': size(file.size) }));
        }
        if (received !== file.size) {
          throw new Error(Drupal.t('only part of it arrived'));
        }
        await writable.close();
      }
      catch (error) {
        await writable.abort().catch(() => {});
        if (error instanceof TypeError) {
          throw new Error(Drupal.t('a network error'));
        }
        throw error;
      }
    }

    async function discardAll() {
      try {
        await post('discard');
        show(Drupal.t('The copies on the server have been deleted.'));
      }
      catch (error) {
        show(error.message, 'error');
      }
    }

    // The zips waiting on the server, with buttons to save them (again), download them or delete them.
    function offerWaiting(waiting, lines = [], kind = 'warning', downloadFirst = false) {
      if (!waiting.length) {
        show(lines.length ? lines : '', kind);
        return;
      }
      const saveButton = [Drupal.t('Save them to a folder…'), async () => {
        let folder = null;
        try {
          folder = await pickFolder();
        }
        catch {
          return; // The folder picker was cancelled.
        }
        setBusy(true);
        try {
          await saveAll(await waitingNow(), folder);
        }
        catch (error) {
          showProgress(null);
          show(error.message, 'error');
        }
        finally {
          setBusy(false);
        }
      }];
      // The ordinary download, for when saving into a folder does not work (2026-11-17).
      const downloadButton = [Drupal.t('Download them instead'), async () => downloadAll(await waitingNow(), '')];
      show(
        [...lines, Drupal.t('Waiting on the server: @files.', { '@files': describe(waiting) })],
        kind,
        [...(downloadFirst ? [downloadButton, saveButton] : [saveButton, downloadButton]), [Drupal.t('Delete them from the server'), discardAll]],
      );
    }

    async function backUp() {
      const chosen = parts();
      if (!chosen.database && !chosen.files) {
        show(Drupal.t('Tick Database, Files or both.'), 'error');
        return;
      }
      let folder = null;
      try {
        folder = await pickFolder();
      }
      catch {
        return; // The folder picker was cancelled.
      }
      setBusy(true);
      try {
        // The server deletes any zips of an earlier backup still waiting, then builds the new ones.
        await post('start', { ...chosen, note: page.querySelector('#backup-note').value });
        show(Drupal.t('Building the backup ...'), 'warning');
        const answer = await follow('backup');
        if (answer.status && answer.status.state === 'failed') {
          throw new Error(Drupal.t('The backup failed: @message', { '@message': answer.status.message }));
        }
        if (!answer.waiting || !answer.waiting.length) {
          throw new Error(Drupal.t('The backup did not arrive on the server.'));
        }
        await saveAll(answer.waiting, folder);
      }
      catch (error) {
        showProgress(null);
        show(error.message, 'error');
      }
      finally {
        setBusy(false);
      }
    }

    // The zips chosen to restore, with what each is (from its name).
    function choose(files) {
      chosenFiles = files;
      const list = document.createElement('ul');
      files.forEach((file) => {
        const item = document.createElement('li');
        item.textContent = `${file.name} (${size(file.size)})`;
        list.append(item);
      });
      const heading = document.createElement('p');
      heading.textContent = Drupal.t('Chosen:');
      find('chosen').replaceChildren(heading, list);
      find('restore-panel').hidden = false;
      page.querySelector('#backup-confirm').focus();
    }

    // Refuses, before uploading anything, zips that are clearly not of one backup (by their names; a renamed zip
    // is left for the server, which checks every zip's manifest).
    function problemWithChoice(files) {
      if (files.length > settings.mostFiles) {
        return Drupal.t('Choose at most @count zips, those of one backup.', { '@count': settings.mostFiles });
      }
      const named = files.map((file) => NAME_PATTERN.exec(file.name)).filter(Boolean);
      if (named.length !== files.length) {
        return null;
      }
      if (new Set(named.map((found) => found[1])).size > 1) {
        return Drupal.t('Those zips come from different backups; choose zips of one backup (their names start the same).');
      }
      if (files.length > 1 && named.some((found) => !found[2])) {
        return Drupal.t('A zip made before backups were split holds the whole backup; restore it alone.');
      }
      if (new Set(named.map((found) => found[2])).size !== files.length) {
        return Drupal.t('The same zip was chosen twice.');
      }
      return null;
    }

    async function pickFile() {
      if (window.showOpenFilePicker) {
        try {
          const handles = await window.showOpenFilePicker({
            id: PICKER_ID,
            multiple: true,
            types: [{ description: Drupal.t('Backup zip'), accept: { 'application/zip': ['.zip'] } }],
          });
          choose(await Promise.all(handles.map((handle) => handle.getFile())));
        }
        catch {
          // The picker was cancelled.
        }
        return;
      }
      find('file').click();
    }

    async function restore() {
      const problem = problemWithChoice(chosenFiles);
      if (problem) {
        show(problem, 'error');
        return;
      }
      if (page.querySelector('#backup-confirm').value.trim() !== 'RESTORE') {
        show(Drupal.t('Type RESTORE in capitals to confirm.'), 'error');
        return;
      }
      setBusy(true);
      try {
        const files = chosenFiles;
        const total = files.reduce((sum, file) => sum + file.size, 0);
        let sentBefore = 0;
        for (const [index, file] of files.entries()) {
          for (let offset = 0; offset < file.size || offset === 0; offset += settings.chunkBytes) {
            await post('upload', file.slice(offset, offset + settings.chunkBytes), `?file=${index}&offset=${offset}`);
            const sent = sentBefore + Math.min(file.size, offset + settings.chunkBytes);
            showProgress(total ? sent / total : 1, Drupal.t('Uploading @name: @done of @total', { '@name': file.name, '@done': size(sent), '@total': size(total) }));
            if (file.size === 0) break;
          }
          sentBefore += file.size;
        }
        showProgress(null);
        await post('restore', { files: files.map((file) => ({ name: file.name, size: file.size })) });
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
    find('file').addEventListener('change', (event) => { if (event.target.files.length) choose([...event.target.files]); });
    find('restore').addEventListener('click', () => { if (!busy && chosenFiles.length) restore(); });

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
        if (answer.waiting && answer.waiting.length) {
          offerWaiting(answer.waiting, [Drupal.t('A backup is waiting on the server (one or more of its zips were not saved).')]);
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
