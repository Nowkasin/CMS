document.addEventListener('DOMContentLoaded', function () {
  const dropzone = document.getElementById('dropzone');
  const fileInput = dropzone ? dropzone.querySelector('input[type=file]') : null;
  const fileNameEl = document.getElementById('fileName');

  if (!dropzone || !fileInput) return;

  fileInput.addEventListener('change', function () {
    if (fileInput.files[0]) {
      fileNameEl.textContent = fileInput.files[0].name;
    }
  });

  ['dragover', 'dragenter'].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.add('drag');
    });
  });

  ['dragleave', 'drop'].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.remove('drag');
    });
  });

  dropzone.addEventListener('drop', function (e) {
    if (e.dataTransfer.files[0]) {
      fileInput.files = e.dataTransfer.files;
      fileNameEl.textContent = e.dataTransfer.files[0].name;
    }
  });
});
