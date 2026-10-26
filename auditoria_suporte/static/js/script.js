/* Interacoes de interface: menu lateral, alertas e confirmacoes. */
(function () {
  "use strict";

  // Menu lateral em telas pequenas
  var toggle = document.getElementById("menuToggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function (evento) {
      evento.stopPropagation();
      sidebar.classList.toggle("aberta");
    });
    document.addEventListener("click", function (evento) {
      if (
        sidebar.classList.contains("aberta") &&
        !sidebar.contains(evento.target) &&
        evento.target !== toggle
      ) {
        sidebar.classList.remove("aberta");
      }
    });
  }

  // Fechar mensagens
  document.querySelectorAll(".fechar-alerta").forEach(function (botao) {
    botao.addEventListener("click", function () {
      var alerta = botao.closest(".alerta");
      if (alerta) {
        alerta.remove();
      }
    });
  });

  // Confirmacao antes de operacoes destrutivas
  document.querySelectorAll("form[data-confirmar]").forEach(function (formulario) {
    formulario.addEventListener("submit", function (evento) {
      if (!window.confirm(formulario.getAttribute("data-confirmar"))) {
        evento.preventDefault();
      }
    });
  });

  // Evita envio duplicado dos formularios de auditoria
  document.querySelectorAll("form").forEach(function (formulario) {
    formulario.addEventListener("submit", function () {
      var botao = formulario.querySelector('button[type="submit"]');
      if (botao && !formulario.hasAttribute("data-confirmar")) {
        setTimeout(function () {
          botao.disabled = true;
          botao.textContent = "Processando...";
        }, 10);
      }
    });
  });

  // Contador de caracteres do conteudo do atendimento
  var conteudo = document.getElementById("conteudo");
  if (conteudo) {
    var contador = document.createElement("small");
    contador.className = "texto-apagado";
    var atualizar = function () {
      contador.textContent = conteudo.value.length + " caractere(s)";
    };
    conteudo.parentNode.appendChild(contador);
    conteudo.addEventListener("input", atualizar);
    atualizar();
  }
})();
