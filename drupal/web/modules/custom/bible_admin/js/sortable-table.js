/**
 * @file
 * Sorts an admin list (a table with the class bible-admin-sortable) by the column whose header is clicked:
 * the first click sorts it A to Z (or smallest first), the second Z to A, the third puts the rows back in
 * the order the page gave them. A header with data-no-sort (Operations) is left alone. The headers are
 * buttons, so the keyboard works too; aria-sort tells a screen reader which column is sorted.
 *
 * A column is sorted as numbers when every filled cell in it is a number ("1,234", "12.5 MB"), else as text
 * (any case, numbers inside text in their natural order).
 */
((Drupal, once) => {
  const NUMBER = /^-?[\d,]+(\.\d+)?(\s*(MB|KB|GB))?$/i;
  const MARKS = { none: '↕', ascending: '▲', descending: '▼' };

  function cellText(row, column) {
    const cell = row.cells[column];
    return cell ? cell.innerText.trim() : '';
  }

  function sortTable(table, column, direction, originalRows) {
    const body = table.tBodies[0];
    let rows = [...originalRows];
    if (direction !== 'none') {
      const texts = rows.map((row) => cellText(row, column));
      const filled = texts.filter((text) => text !== '');
      const isNumbers = filled.length > 0 && filled.every((text) => NUMBER.test(text));
      const value = (row) => {
        const text = cellText(row, column);
        return isNumbers ? parseFloat(text.replace(/,/g, '')) || 0 : text;
      };
      const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
      rows.sort((first, second) => {
        const firstValue = value(first);
        const secondValue = value(second);
        const order = isNumbers ? firstValue - secondValue : collator.compare(firstValue, secondValue);
        return direction === 'ascending' ? order : -order;
      });
    }
    rows.forEach((row) => body.appendChild(row));
  }

  Drupal.behaviors.bibleAdminSortableTable = {
    attach(context) {
      once('bible-admin-sortable', 'table.bible-admin-sortable', context).forEach((table) => {
        const body = table.tBodies[0];
        const headers = table.tHead ? [...table.tHead.rows[0].cells] : [];
        // The "There are none" row is one cell across the table: nothing to sort.
        if (!body || headers.length === 0 || body.rows.length < 2) {
          return;
        }
        const originalRows = [...body.rows];
        const state = { column: -1, direction: 'none' };

        headers.forEach((header, column) => {
          if (header.hasAttribute('data-no-sort')) {
            return;
          }
          const label = header.textContent.trim();
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'bible-admin-sort-button';
          button.title = Drupal.t('Sort by @label (click again to reverse, a third time to clear)', { '@label': label });
          const mark = document.createElement('span');
          mark.className = 'bible-admin-sort-mark';
          mark.setAttribute('aria-hidden', 'true');
          button.textContent = label;
          button.appendChild(mark);
          header.textContent = '';
          header.appendChild(button);

          button.addEventListener('click', () => {
            if (state.column !== column) {
              state.column = column;
              state.direction = 'ascending';
            }
            else {
              state.direction = { ascending: 'descending', descending: 'none', none: 'ascending' }[state.direction];
            }
            sortTable(table, column, state.direction, originalRows);
            headers.forEach((other, index) => {
              const otherMark = other.querySelector('.bible-admin-sort-mark');
              const direction = index === column ? state.direction : 'none';
              if (direction === 'none') {
                other.removeAttribute('aria-sort');
              }
              else {
                other.setAttribute('aria-sort', direction);
              }
              if (otherMark) {
                otherMark.textContent = ' ' + MARKS[direction];
                otherMark.classList.toggle('is-active', direction !== 'none');
              }
            });
          });
          mark.textContent = ' ' + MARKS.none;
        });
      });
    },
  };
})(Drupal, once);
