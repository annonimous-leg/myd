import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const SOURCE_TEXT = [
  "Convocatoria sintética para aceptación del workspace de licitante.",
  "Este archivo es un fixture de CI: no es una convocatoria oficial ni una fuente normativa.",
  "Versión: CI-1",
  "",
  "REQUISITOS DE PARTICIPACIÓN",
  "1. Integrar un programa de obra con actividades, duración y precedencias verificables.",
  "2. Documentar cantidades y precios unitarios con sus fuentes y trazabilidad.",
  "ANEXOS",
  "Contenido meramente ilustrativo.",
  "",
].join("\n");

export async function licitacionFlow({ browser, credentials, origin, evidence, login }) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
  });
  await context.tracing.start({ screenshots: true, snapshots: true });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));

  try {
    assert.ok(credentials.bidder, "CI must seed a dedicated technician/bidder identity.");
    assert.ok(credentials.bidder_profile_code, "CI must seed a synthetic jurisdiction profile.");
    await login(page, credentials.bidder);
    await page.getByRole("navigation").getByRole("button", { name: "Proyectos", exact: true }).click();
    await page.getByRole("button", { name: "Nuevo", exact: true }).click();
    await page.getByLabel("Título del expediente").fill("Preparación sintética de propuesta CI");
    await page.getByLabel("Órgano", { exact: false }).fill("CI sintético — no es convocante real");
    await page.getByLabel("Unidad administrativa").fill("Aceptación del workspace de licitante");
    await page.getByLabel("Serie documental", { exact: false }).first().fill("CI-BIDDER");
    await page.getByLabel("Subserie documental", { exact: false }).fill("CI-BIDDER-SOURCE");

    const [createdExpediente] = await Promise.all([
      page.waitForResponse((response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/expedientes",
      ),
      page.getByRole("button", { name: "Crear expediente", exact: true }).click(),
    ]);
    assert.ok(createdExpediente.ok(), await createdExpediente.text());
    const expediente = await createdExpediente.json();
    const apiOrigin = new URL(createdExpediente.url()).origin;
    assert.ok(expediente.id, "The real expediente endpoint must return a persisted ID.");

    await page.getByRole("navigation").getByRole("button", { name: "Licitaciones de Obra", exact: true }).click();
    await page.getByRole("heading", { name: "Automatización de proposición", exact: true }).waitFor();
    await page.getByText("Modo licitante", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Emitir fallo oficial", exact: true }).count(), 0);
    assert.equal(await page.getByRole("button", { name: "Crear contrato oficial", exact: true }).count(), 0);
    assert.equal(await page.getByRole("button", { name: "Cerrar finiquito", exact: true }).count(), 0);

    const catalogResponse = await page.request.get(apiOrigin + "/api/v1/procurement/catalog");
    assert.equal(catalogResponse.status(), 200, await catalogResponse.text());
    const catalog = await catalogResponse.json();
    const profileCode = credentials.bidder_profile_code;
    const profile = (catalog.profiles || []).find((item) => item.code === profileCode);
    assert.ok(profile, "The CI jurisdiction profile " + profileCode + " must exist in the tenant catalog.");
    assert.equal(profile.ready_for_execution, true, JSON.stringify(profile.readiness_reasons || []));
    assert.equal(profile.tenant_scope, "TENANT");
    assert.ok((profile.rule_count || 0) >= 1);
    assert.ok((profile.source_count || 0) >= 1);
    assert.ok((profile.article_count || 0) >= 1);
    assert.ok((profile.bound_rule_article_count || 0) >= 1);

    const jurisdiction = page.getByLabel("Jurisdicción y régimen de la convocatoria");
    await jurisdiction.locator("option").filter({ hasText: profileCode }).waitFor({ state: "attached" });
    await jurisdiction.selectOption(profileCode);
    await page.getByLabel("Identificador de licitación").fill("CI-BIDDER-" + String(expediente.id).slice(0, 8));
    await page.getByLabel("Nombre / objeto de la obra").fill("Preparación de propuesta propia — caso sintético CI");
    await page.getByLabel("Monto estimado").fill("120000");
    await page.getByRole("button", { name: "Crear expediente de automatización", exact: true }).waitFor();
    await page.waitForFunction(
      () => [...document.querySelectorAll("button")].some(
        (button) => button.textContent?.trim() === "Crear expediente de automatización" && !button.disabled,
      ),
    );

    const [createdTenderResponse] = await Promise.all([
      page.waitForResponse((response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/procurement/tenders",
      ),
      page.getByRole("button", { name: "Crear expediente de automatización", exact: true }).click(),
    ]);
    assert.equal(createdTenderResponse.status(), 201, await createdTenderResponse.text());
    const tender = await createdTenderResponse.json();
    assert.ok(tender.id);
    assert.equal(tender.expediente_id, expediente.id);
    assert.equal(tender.jurisdiction_code, profileCode);
    // A newly created tender stays in the proposal panel. The separate document
    // editor is entered explicitly with "Abrir Documentos" after creating an annex.
    await page.getByRole("heading", { name: "Automatización de proposición", exact: true }).waitFor();
    await page.getByRole("heading", { name: "1. Fuentes", exact: true }).waitFor();

    const sourceBuffer = Buffer.from(SOURCE_TEXT, "utf8");
    const expectedHash = createHash("sha256").update(sourceBuffer).digest("hex");
    await page.locator('input[type="file"]').first().setInputFiles({
      name: "convocatoria-ci.txt",
      mimeType: "text/plain",
      buffer: sourceBuffer,
    });
    const [sourceResponse] = await Promise.all([
      page.waitForResponse((response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v1/procurement/tenders/" + tender.id + "/sources",
      ),
      page.getByRole("button", { name: "Ingresar fuentes", exact: true }).click(),
    ]);
    assert.equal(sourceResponse.status(), 201, await sourceResponse.text());
    const sourceResult = await sourceResponse.json();
    assert.equal(sourceResult.sha256, expectedHash);
    assert.ok(sourceResult.evidence_id);
    assert.ok(sourceResult.storage_path);
    assert.equal(sourceResult.size_bytes, sourceBuffer.byteLength);

    const storedTenderResponse = await page.request.get(apiOrigin + "/api/v1/procurement/tenders/" + tender.id);
    assert.equal(storedTenderResponse.status(), 200, await storedTenderResponse.text());
    const storedTender = await storedTenderResponse.json();
    const sourceManifestEntry = (storedTender.source_manifest?.sources || []).find(
      (source) => source.sha256 === expectedHash,
    );
    assert.ok(sourceManifestEntry, "The uploaded source hash must be bound to the persisted tender manifest.");
    assert.equal(sourceManifestEntry.filename, "convocatoria-ci.txt");
    assert.equal(sourceManifestEntry.source_role, "CONVOCATORIA");

    const readinessResponse = await page.request.get(
      apiOrigin + "/api/v1/procurement/tenders/" + tender.id + "/readiness",
    );
    assert.equal(readinessResponse.status(), 200, await readinessResponse.text());
    const readiness = await readinessResponse.json();
    assert.equal(readiness.source_readiness.ready, true);
    assert.deepEqual(readiness.source_readiness.missing_source_roles, []);
    assert.equal(readiness.source_readiness.candidate_count, 2);
    assert.equal(readiness.source_readiness.confirmed_candidate_count, 0);
    assert.equal(readiness.ready, false, "Source extraction must not make a bid ready without human requirement confirmation.");
    assert.ok(readiness.findings.some((finding) => finding.code === "REQUIREMENT_REVIEW_REQUIRED"));
    await page.getByText(/REQUIREMENT_REVIEW_REQUIRED/).waitFor();

    const candidateResponse = await page.request.get(
      apiOrigin + "/api/v1/procurement/tenders/" + tender.id + "/requirements/candidates",
    );
    assert.equal(candidateResponse.status(), 200, await candidateResponse.text());
    const candidates = await candidateResponse.json();
    assert.equal(candidates.length, 2);
    assert.ok(candidates.every((candidate) => candidate.status === "REVIEW_REQUIRED"));

    // Human review is an explicit step: edit/confirm each source-grounded requirement
    // and its mandatory status before it can become effective.
    await page.getByRole("heading", { name: "2. Revisar requisitos extraídos", exact: true }).waitFor();
    for (const candidate of candidates) {
      await page.getByLabel("Descripción del requisito " + candidate.code + " — fuente " + candidate.candidate_id.slice(-8), { exact: true })
        .fill(candidate.description + " — revisado por el licitante");
      await page.getByLabel("Categoría del requisito " + candidate.code + " — fuente " + candidate.candidate_id.slice(-8), { exact: true })
        .selectOption(candidate.category || "ADMINISTRATIVO");
      await page.getByLabel("Obligatoriedad del requisito " + candidate.code + " — fuente " + candidate.candidate_id.slice(-8), { exact: true })
        .selectOption("true");
    }

    const [confirmedResponse] = await Promise.all([
      page.waitForResponse((response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname ===
          "/api/v1/procurement/tenders/" + tender.id + "/requirements/candidates/confirm",
      ),
      page.getByRole("button", { name: "Confirmar requisitos revisados", exact: true }).click(),
    ]);
    assert.equal(confirmedResponse.status(), 200, await confirmedResponse.text());
    const confirmedCandidates = await confirmedResponse.json();
    assert.equal(confirmedCandidates.length, 2);
    assert.ok(confirmedCandidates.every((candidate) =>
      candidate.status === "CONFIRMED" && candidate.mandatory === true &&
      candidate.source_reference.confirmation_required === false &&
      candidate.source_reference.confirmed_by_user_id,
    ));
    await page.getByText("2 requisitos confirmados por el licitante", { exact: true }).waitFor();

    const confirmedReadinessResponse = await page.request.get(
      apiOrigin + "/api/v1/procurement/tenders/" + tender.id + "/readiness",
    );
    assert.equal(confirmedReadinessResponse.status(), 200, await confirmedReadinessResponse.text());
    const confirmedReadiness = await confirmedReadinessResponse.json();
    assert.equal(confirmedReadiness.source_readiness.confirmed_candidate_count, 2);
    assert.ok(!confirmedReadiness.findings.some((finding) => finding.code === "REQUIREMENT_REVIEW_REQUIRED"));

    // Exercise the versioned workspace-document API and verify its presence
    // in the current browser annex UI. Arbitrary text/plain documents do not
    // have an editable field map in the template-driven visual editor.
    const workspaceCreateResponse = await page.request.post(
      apiOrigin + "/api/v1/procurement/tenders/" + tender.id + "/workspace/documents",
      {
        headers: { Origin: origin },
        data: {
          artifact_code: "CI-TECHNICAL-MEMO",
          name: "Memorando técnico sintético de aceptación",
          media_type: "text/plain",
        },
      },
    );
    assert.equal(workspaceCreateResponse.status(), 201, await workspaceCreateResponse.text());
    const workspaceDocument = await workspaceCreateResponse.json();
    assert.equal(workspaceDocument.version, 1);
    assert.equal(workspaceDocument.human_modified, false);
    const humanText = "NOTA DE TRABAJO CI: revisar el programa, el presupuesto y los anexos antes de presentar.";
    const workspaceUrl = apiOrigin + "/api/v1/procurement/tenders/" + tender.id +
      "/workspace/documents/" + workspaceDocument.id;
    const workspaceUpdateResponse = await page.request.put(workspaceUrl, {
      headers: { Origin: origin },
      data: { content_text: humanText, content_model: {}, expected_row_version: workspaceDocument.row_version },
    });
    assert.equal(workspaceUpdateResponse.status(), 200, await workspaceUpdateResponse.text());
    const updatedWorkspaceDocument = await workspaceUpdateResponse.json();
    // A stale edit cannot silently overwrite the accepted human revision.
    const staleUpdateResponse = await page.request.put(workspaceUrl, {
      headers: { Origin: origin },
      data: { content_text: "sobrescritura obsoleta", content_model: {}, expected_row_version: workspaceDocument.row_version },
    });
    assert.equal(staleUpdateResponse.status(), 409, await staleUpdateResponse.text());
    // Check actual navigation and revision visibility in the current browser UI.
    const refreshedDocuments = page.waitForResponse((response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname ===
        "/api/v1/procurement/tenders/" + tender.id + "/workspace/documents",
    );
    await page.getByRole("button", { name: "Actualizar workspace de licitación", exact: true }).click();
    assert.equal((await refreshedDocuments).status(), 200);
    await page.getByRole("button", { name: "Abrir Documentos", exact: true }).click();
    await page.getByRole("heading", { name: "Documentos", exact: true }).waitFor();
    await page.getByRole("navigation", { name: "Anexos de la propuesta" })
      .getByRole("button", { name: /CI-TECHNICAL-MEMO/ }).click();
    await page.getByText("Revisión 2", { exact: true }).waitFor();
    await page.getByText("El perfil de este formato no tiene campos habilitados para editar.", { exact: true }).waitFor();
    assert.equal(updatedWorkspaceDocument.version, 2);
    assert.equal(updatedWorkspaceDocument.human_modified, true);
    assert.equal(updatedWorkspaceDocument.status, "DRAFT");
    assert.equal(updatedWorkspaceDocument.content_text, humanText);
    const workspaceHistoryResponse = await page.request.get(
      apiOrigin + "/api/v1/procurement/tenders/" + tender.id +
        "/workspace/documents/" + workspaceDocument.id + "/history",
    );
    assert.equal(workspaceHistoryResponse.status(), 200, await workspaceHistoryResponse.text());
    const workspaceHistory = await workspaceHistoryResponse.json();
    assert.deepEqual(workspaceHistory.map((entry) => entry.version), [2, 1]);
    assert.equal(workspaceHistory[0].operation, "HUMAN_EDIT");
    assert.equal(workspaceHistory[0].human_modified, true);
    assert.equal(workspaceHistory[1].operation, "CREATE");

    // A reviewer may ask for a package only after the tender reaches HUMAN_APPROVAL.
    // This check proves the service-side gate, not just the disabled frontend button.
    const reviewerContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    try {
      const reviewerPage = await reviewerContext.newPage();
      await login(reviewerPage, credentials.reviewer);
      const prematureSubmission = await reviewerPage.request.post(
        apiOrigin + "/api/v1/procurement/tenders/" + tender.id + "/submission",
        { headers: { Origin: origin } },
      );
      assert.equal(prematureSubmission.status(), 409, await prematureSubmission.text());
      const prematureBody = await prematureSubmission.json();
      assert.match(JSON.stringify(prematureBody), /HUMAN_APPROVAL|aprobación humana/i);
    } finally {
      await reviewerContext.close();
    }

    // Authority-side routes must be absent at runtime, independently of
    // whether the deployment publishes its OpenAPI document.
    const legacyCalls = [
      ["GET", "/api/v1/licitaciones"],
      ["POST", "/api/v1/licitaciones"],
      ["GET", "/api/v1/contratos"],
      ["POST", "/api/v1/contratos"],
      ["POST", "/api/v1/licitaciones-obra/expediente/" + expediente.id + "/planeacion"],
      ["POST", "/api/v1/licitaciones-obra/expediente/" + expediente.id + "/fallo"],
      ["POST", "/api/v1/licitaciones-obra/expediente/" + expediente.id + "/contrato"],
      ["POST", "/api/v1/licitaciones-obra/expediente/" + expediente.id + "/finiquito"],
    ];
    for (const [method, path] of legacyCalls) {
      // Send the configured frontend Origin so CSRF validation passes and
      // this assertion reaches the router's bidder-only 404 boundary.
      const response = await page.request.fetch(apiOrigin + path, {
        method,
        headers: { Origin: origin },
      });
      assert.equal(response.status(), 404, method + " " + path + ": " + await response.text());
    }

    assert.deepEqual(errors, []);
    await page.screenshot({ path: join(evidence, "13-bidder-workspace.png"), fullPage: true });
    await page.screenshot({ path: join(evidence, "14-source-requirement-gate.png"), fullPage: true });
  } finally {
    await page.screenshot({ path: join(evidence, "bidder-last-screen.png"), fullPage: true }).catch(() => {});
    await context.tracing.stop({ path: join(evidence, "bidder-flow-trace.zip") }).catch(() => {});
    await context.close();
  }
}
