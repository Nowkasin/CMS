// หน้า upload.html (Step 1) -- dropzone เลือก/ลาก-วางไฟล์ Excel
(function () {
  const fileInput = document.querySelector('#uploadForm input[type="file"]');
  const dzEmpty = document.getElementById("dzEmpty");
  const dzFile = document.getElementById("dzFile");
  const dzFileName = document.getElementById("dzFileName");
  const dropzone = document.getElementById("dropzone");

  function showFile(file) {
    dzFileName.textContent = file.name;
    dzEmpty.classList.add("hidden");
    dzFile.classList.remove("hidden");
  }

  function resetDropzone() {
    fileInput.value = "";
    dzEmpty.classList.remove("hidden");
    dzFile.classList.add("hidden");
  }

  fileInput?.addEventListener("change", () => {
    if (fileInput.files[0]) showFile(fileInput.files[0]);
  });

  document
    .getElementById("btnChangeFile")
    ?.addEventListener("click", () => fileInput.click());
  document
    .getElementById("btnRemoveFile")
    ?.addEventListener("click", resetDropzone);

  dropzone?.addEventListener("click", (e) => {
    if (e.target.closest("#btnChangeFile") || e.target.closest("#btnRemoveFile")) return;
    fileInput.click();
  });

  ["dragover", "dragenter"].forEach((ev) =>
    dropzone?.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("border-brand-500");
    }),
  );

  ["dragleave", "drop"].forEach((ev) =>
    dropzone?.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("border-brand-500");
    }),
  );

  dropzone?.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) {
      fileInput.files = e.dataTransfer.files;
      showFile(f);
    }
  });
})();
