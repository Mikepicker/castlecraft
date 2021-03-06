import copy
import operator
import xml.etree.ElementTree as ET
from functools import reduce

INPUT_NAME = 'Walking.dae'
OUTPUT_NAME = 'character'

# strip namespace from tags
tree = ET.ElementTree(file=INPUT_NAME)
for el in tree.iter():
    if '}' in el.tag:
        el.tag = el.tag.split('}', 1)[1]

# root node
root = tree.getroot()

# library nodes
library_geometries = root.find('library_geometries')
library_images = root.find('library_images')
library_materials = root.find('library_materials')
library_effects = root.find('library_effects')
library_vs = root.find('library_visual_scenes')
library_controllers = root.find('library_controllers')
library_anim = root.find('library_animations')

# ----------------- UTILS ----------------- #
def safe_split(l):
    res = l.replace('\n', ' ').split(' ')
    res = [x for x in res if x] # clean array from empty strings
    return res

# ----------------- MATERIALS DATA ----------------- #
def extract_newparams(effect_node):
    profile_common_node = effect_node.find('profile_COMMON')

    if (profile_common_node == None):
        print('[extract_newparams] Unsupported profile')
        exit()

    newparams = {}
    newparam_nodes = profile_common_node.findall('newparam')

    for n in newparam_nodes:
        newparam_id = n.attrib['sid']

        child_node = list(list(n)[0])[0]
        if 'source' in child_node.tag: # ref to another newparam
            newparams[newparam_id] = effect_node.find('.//newparam[@sid="' + child_node.text + '"]').find('.//init_from').text
        elif 'init_from' in child_node.tag:
            newparams[newparam_id] = child_node.text
        elif 'instance_image' in child_node.tag:
            newparams[newparam_id] = child_node.attrib['url'][1:]

    return newparams

def extract_technique(effect_node, newparams, textures):
    technique = []

    # get params
    phong_node = effect_node.find('.//lambert') or effect_node.find('.//phong') or effect_node.find('.//blinn')
    param_nodes = list(phong_node)
    for p_node in param_nodes:

        # can be texture, color, float
        texture_node = p_node.find('texture')
        color_node = p_node.find('color')
        float_node = p_node.find('float')

        p_tag = p_node.tag

        if texture_node != None:
            texture_id = newparams[texture_node.attrib['texture']]
            technique.append({ 'id': p_tag, 'value': textures[texture_id] , 'type': 'texture' })
        elif color_node != None:
            rgba = safe_split(color_node.text)
            technique.append({ 'id': p_tag, 'value': { 'r': rgba[0], 'g': rgba[1], 'b': rgba[2], 'a': rgba[3] }, 'type': 'rgba' })
        else:
            technique.append({ 'id': p_tag, 'value': float_node.text, 'type': 'float' })

    # get normal maps
    normal_node = effect_node.find('.//displacement')
    if normal_node != None:
        texture_node = normal_node.find('texture')
        texture_id = newparams[texture_node.attrib['texture']]
        technique.append({ 'id': 'normal', 'value': textures[texture_id] , 'type': 'texture' })

    return technique

def extract_materials():
    # get all textures
    textures = {}
    if library_images != None:
        image_nodes = list(library_images)
        for i_node in image_nodes:
            init_from_node = i_node.find('init_from')
            ref_node = init_from_node.find('ref')
            textures[i_node.attrib['id']] = ref_node.text if ref_node != None else init_from_node.text
    else:
        print("[extract_materials] No images")

    if library_effects == None:
        print('[extract_materials] No effects')
        return []

    # effects
    effects = {}
    effects_node = library_effects.findall('effect')
    for e_node in effects_node:
        effect_id = e_node.attrib['id']

        # parse newparams (needed to link textures)
        newparams = extract_newparams(e_node)

        # parse techniques (diffuse, ambient ecc..)
        effects[effect_id] = extract_technique(e_node, newparams, textures)


    # combine materials
    materials = []
    material_nodes = library_materials.findall('material')
    for m_node in material_nodes:
        effect_id = m_node.find('instance_effect').attrib['url'][1:]
        materials.append({ 'id': m_node.attrib['id'], 'name': m_node.attrib['name'], 'params': effects[effect_id] })

    return materials

# ----------------- GEOMETRY DATA ----------------- #
# vertices, normals, uvs, materials
def extract_positions(mesh_node, poly_node):
    data = []

    positions_source = poly_node.find('.//input[@semantic="VERTEX"]').attrib['source'][1:]
    positions_id = mesh_node.find('.//vertices').find('input[@semantic="POSITION"]').attrib['source'][1:]
    node = mesh_node.find('.//source[@id="' + positions_id + '"]').find('float_array')

    count = int(node.attrib['count'])
    array = safe_split(node.text)
    
    for i in range(int(count / 3)):
        x = float(array[i * 3 + 0])
        y = float(array[i * 3 + 1])
        z = float(array[i * 3 + 2])
        data.append({ "x": x, "y": y, "z": z })

    return data

def extract_normals(mesh_node, poly_node):
    data = []

    normals_id = poly_node.find('.//input[@semantic="NORMAL"]').attrib['source'][1:]
    node = mesh_node.find('.//source[@id="' + normals_id + '"]').find('float_array')

    count = int(node.attrib['count'])
    array = safe_split(node.text)
    
    for i in range(int(count / 3)):
        x = float(array[i * 3])
        y = float(array[i * 3 + 1])
        z = float(array[i * 3 + 2])
        data.append({ "x": x, "y": y, "z": z })

    return data

def extract_uvs(mesh_node, poly_node):
    data = []

    uvs_id = poly_node.find('.//input[@semantic="TEXCOORD"]').attrib['source'][1:]
    node = mesh_node.find('.//source[@id="' + uvs_id + '"]').find('float_array')

    count = int(node.attrib['count'])
    array = safe_split(node.text)
    
    for i in range (int(count / 2)):
        u = float(array[i * 2])
        v = float(array[i * 2 + 1])
        data.append({ "u": u, "v": v })

    return data

def extract_faces(mesh_node, poly_node):
    data = []

    type_count = len(poly_node.findall('input'))
    index_data = safe_split(poly_node.find('p').text)

    for i in range(int(len(index_data) / type_count)):
        p_index = index_data[i * type_count + 0]
        n_index = index_data[i * type_count + 1]
        u_index = index_data[i * type_count + 2]
        data.append({ "p_index": p_index, "n_index": n_index, "u_index": u_index })

    return data

def extract_geometry():
    res = []

    geometries = library_geometries.findall('geometry')

    for geometry in geometries:
        mesh_node = geometry.find('mesh')
        poly_node = mesh_node.find('triangles') or mesh_node.find('polylist')

        # raw data
        positions = extract_positions(mesh_node, poly_node)
        normals = extract_normals(mesh_node, poly_node)
        uvs = extract_uvs(mesh_node, poly_node)

        # faces
        faces = extract_faces(mesh_node, poly_node)

        # material
        material_id = -1
        if 'material' in poly_node.attrib:
            material_symbol = poly_node.attrib['material']
            material_id = library_vs.find('.//instance_material').attrib['target'][1:]

        res.append({ "positions": positions, "normals": normals, "uvs": uvs, "faces": faces, "material_id": material_id })

    return res

# ----------------- SKIN DATA ----------------- #
# joints list and vertex weights

def get_max_weight(l):
    m = 0
    for i in range(len(l)):
        if l[i]['weight'] > l[m]['weight']:
            m = i
    
    return m

def limit_vertex_data(vertex_data):
    vertex_data = sorted(vertex_data, key=lambda k: k['weight'], reverse=True)
    res = vertex_data

    # len < 3
    if len(vertex_data) == 1:
        res.append(copy.deepcopy(res[0]))
        res[1]['weight'] = 0
        res.append(copy.deepcopy(res[0]))
        res[2]['weight'] = 0
    elif len(vertex_data) == 2:
        res.append(copy.deepcopy(res[0]))
        res[2]['weight'] = 0
    elif len(res) > 3:
        # res = res[:3]
        g3 = []
        for i in range(3):
            g3.append(res.pop(get_max_weight(res)))
        res = g3

    # make sum add up to 1
    total = sum(list(map(lambda x: float(x['weight']), res)))
    for v in res:
       v['weight'] = float(v['weight']) / total

    return res

def extract_joints():
    joints_data = []
    controller = library_controllers.find('controller')
    joints_id = library_controllers.find('.//joints').find('input[@semantic="JOINT"]').attrib['source'][1:]
    joints_tag = library_controllers.find('.//source[@id="' + joints_id + '"]').find('Name_array')
    joints = joints_tag.text.split()

    i = 0
    for joint_name in joints:
        data = joint_name
        joints_data.insert(i, data)
        i += 1

    return joints_data

def extract_inv_joints():
    joints_inv_data = []

    joints_inv_id = library_controllers.find('.//joints').find('input[@semantic="INV_BIND_MATRIX"]').attrib['source'][1:]
    joints_inv_tag = library_controllers.find('.//source[@id="' + joints_inv_id + '"]').find('float_array')
    joints_inv = safe_split(joints_inv_tag.text)

    for i in range(int(len(joints_inv) / 16)):
        t = []
        t.append(joints_inv[i * 16 + 0])
        t.append(joints_inv[i * 16 + 1])
        t.append(joints_inv[i * 16 + 2])
        t.append(joints_inv[i * 16 + 3])
        t.append(joints_inv[i * 16 + 4])
        t.append(joints_inv[i * 16 + 5])
        t.append(joints_inv[i * 16 + 6])
        t.append(joints_inv[i * 16 + 7])
        t.append(joints_inv[i * 16 + 8])
        t.append(joints_inv[i * 16 + 9])
        t.append(joints_inv[i * 16 + 10])
        t.append(joints_inv[i * 16 + 11])
        t.append(joints_inv[i * 16 + 12])
        t.append(joints_inv[i * 16 + 13])
        t.append(joints_inv[i * 16 + 14])
        t.append(joints_inv[i * 16 + 15])
    
        joints_inv_data.append(t)

    return joints_inv_data

def extract_vertex_weights():
    weights_data = []

    weights_data_id = library_controllers.find('.//input[@semantic="WEIGHT"]').attrib['source'][1:]
    weights = library_controllers.find('.//source[@id="' + weights_data_id + '"]').find('.//float_array').text.split()

    vertex_weights_tag = root.find('.//vertex_weights')
    counts = vertex_weights_tag.find('vcount').text.split()
    weights_map = vertex_weights_tag.find('v').text.split() # [joint_id, weight_id]

    pointer = 0
    vertex_id = 0
    for count in counts:
        vertex_data = []
        for w in range(int(count)):
            joint_id = int(weights_map[pointer])
            pointer += 1
            weight_id = int(weights_map[pointer])
            pointer += 1
            vertex_data.append({ "vertex_id": vertex_id, "joint_id": joint_id, "weight": weights[int(weight_id)] })

        # get only first 3 weights
        vertex_data = limit_vertex_data(vertex_data)

        weights_data += vertex_data

        vertex_id += 1

    return weights_data

# ----------------- SKELETON DATA ----------------- #
# joints hierarchy and transforms

def extract_joint_data(joints, joint_node):
    joint_name = joint_node.attrib['sid']
    
    if joint_name not in joints:
        print("[extract_joint_data] skipping " + joint_name)
        return None

    index = joints.index(joint_name)
    matrix_data = joint_node.find('matrix').text.split(' ')

    children_data = []
    children_nodes = joint_node.findall('node')
    for child in children_nodes:
        res = extract_joint_data(joints, child)
        if res != None:
            res["parent_id"] = index
            children_data.append(res)

    return { "joint_id": index,  "joint_name": joint_name, "transform": matrix_data, "parent_id": -1, "children": children_data }

def extract_skeleton(joints):
    skeleton = []

    skeleton_node = library_vs.find('.//skeleton')
    head_joint_node = library_vs.find('.//node[@id="' + skeleton_node.text[1:] + '"]')

    head_joint_data = extract_joint_data(joints, head_joint_node) 
    skeleton.append(head_joint_data)

    return skeleton

# ----------------- ANIMATION DATA ----------------- #
# keyframes list, joint transforms for each keyframes, total duration
def extract_animations(joints):
    keyframes = []
    transforms = []
    duration = 0
     
    keyframes = safe_split(library_anim.find('animation').find('.//source').find('float_array').text.replace('\n', ' '))

    duration = keyframes[len(keyframes) - 1]

    animation_nodes = library_anim.findall('animation')
    for joint_node in animation_nodes:
        joint_name = joint_node.find('channel').attrib['target'].split('/')[0]
        joint_data_sid = library_vs.find('.//node[@id="' + joint_name + '"]').attrib['sid']
        joint_data_id = joint_node.find('sampler').find('.//input[@semantic="OUTPUT"]').attrib['source'][1:]
        joint_data_float_array = joint_node.find('.//source[@id="' + joint_data_id + '"]').find('float_array')
        joint_transforms = safe_split(joint_data_float_array.text)

        # transform matrix for each keyframe
        transforms_out = []
        for i in range(int(len(joint_transforms) / 16)):
            t = []
            t.append(joint_transforms[i * 16 + 0])
            t.append(joint_transforms[i * 16 + 1])
            t.append(joint_transforms[i * 16 + 2])
            t.append(joint_transforms[i * 16 + 3])
            t.append(joint_transforms[i * 16 + 4])
            t.append(joint_transforms[i * 16 + 5])
            t.append(joint_transforms[i * 16 + 6])
            t.append(joint_transforms[i * 16 + 7])
            t.append(joint_transforms[i * 16 + 8])
            t.append(joint_transforms[i * 16 + 9])
            t.append(joint_transforms[i * 16 + 10])
            t.append(joint_transforms[i * 16 + 11])
            t.append(joint_transforms[i * 16 + 12])
            t.append(joint_transforms[i * 16 + 13])
            t.append(joint_transforms[i * 16 + 14])
            t.append(joint_transforms[i * 16 + 15])
        
            transforms_out.append(t)

        transforms.append({ "joint_id": joints.index(joint_data_sid), "transforms": transforms_out })

    return { "keyframes": keyframes, "animations": transforms, "duration": duration }


# ----------------- EXPORT OBJ ----------------- #
def export_obj(geometry, materials):
    obj_out = open(OUTPUT_NAME + '.obj', 'w')

    has_materials = len(materials) > 0

    # output mtl reference
    if has_materials:
        obj_out.write('mtllib ' + OUTPUT_NAME + '.mtl\n')
    
    for group in geometry:
        # output positions
        for p in group['positions']:
            obj_out.write('v ' + str(p['x']) + ' ' + str(p['y']) + ' ' + str(p['z']) + '\n') 

    for group in geometry:
        # output normals
        for n in group['normals']:
            obj_out.write('vn ' + str(n['x']) + ' ' + str(n['y']) + ' ' + str(n['z']) + '\n') 

    for group in geometry:
        # output texcoords
        for u in group['uvs']:
            obj_out.write('vt ' + str(u['u']) + ' ' + str(u['v']) + '\n') 

    geom_index = 0
    p_offset = 0 # position offset 
    u_offset = 0 # texcoord offset
    n_offset = 0 # normal offset
    for group in geometry:
        # output material
        if has_materials and group['material_id'] != None:
            obj_out.write('usemtl ' + group['material_id'] + '\n')

        # output faces
        faces = group['faces']

        for i in range(int(len(faces) / 3)):
            line = 'f'
            line += ' ' + str(int(faces[i * 3 + 0]['p_index']) + 1 + p_offset) + '/' + str(int(faces[i * 3 + 0]['u_index']) + 1 + u_offset) + '/' + str(int(faces[i * 3 + 0]['n_index']) + 1 + n_offset)
            line += ' ' + str(int(faces[i * 3 + 1]['p_index']) + 1 + p_offset) + '/' + str(int(faces[i * 3 + 1]['u_index']) + 1 + u_offset) + '/' + str(int(faces[i * 3 + 1]['n_index']) + 1 + n_offset)
            line += ' ' + str(int(faces[i * 3 + 2]['p_index']) + 1 + p_offset) + '/' + str(int(faces[i * 3 + 2]['u_index']) + 1 + u_offset) + '/' + str(int(faces[i * 3 + 2]['n_index']) + 1 + n_offset)
            line += '\n'
            obj_out.write(line)

        geom_index += 1
        last_geom = geometry[geom_index - 1]
        p_offset += len(last_geom['positions'])
        u_offset += len(last_geom['uvs'])
        n_offset += len(last_geom['normals'])

    obj_out.close()

    # output mtl
    mtl_out = open(OUTPUT_NAME + '.mtl', 'w')

    conv_map = {
        'emission': 'Ke',
        'ambient': 'Ka',
        'diffuse': 'Kd',
        'specular': 'Ks',
        'shininess': 'Ns',
        'transparency': 'd',
        'normal': 'Kn'
    }

    skip_list = ['reflectivity', 'reflective', 'transparent', 'index_of_refraction']

    for m in materials:
        mtl_out.write('newmtl ' + str(m['id']) + '\n')

        for p in m['params']:
            if p['id'] in skip_list:
                continue

            if p['type'] == 'texture':
                mtl_out.write('map_' + conv_map[p['id']] + ' ' + p['value'] + '\n')
            elif p['type'] == 'rgba':
                mtl_out.write(conv_map[p['id']] + ' ' + p['value']['r'] + ' ' + p['value']['g'] + ' ' + p['value']['b'] + '\n')
            elif p['type'] == 'float':
                mtl_out.write(conv_map[p['id']] + ' ' + p['value'] + '\n')

    mtl_out.close()

# ----------------- EXPORT SKL ----------------- #
def write_skeleton(skeleton, skl_out):
    for j in skeleton:
        skl_out.write(str(j['joint_id']) + ' ' + str(j['joint_name']) + ' ' + str(j['parent_id']) + ' ' + ' '.join(j['transform']) + '\n')
        write_skeleton(j['children'], skl_out)

def export_skl(weights, skeleton, joints_inv):
    skl_out = open(OUTPUT_NAME + '.skl', 'w')

    # joint_id joint_name parent_id transform
    skl_out.write('joints\n')
    write_skeleton(skeleton, skl_out)

    # joints_inv
    skl_out.write('bindpose_inv\n')
    joint_id = 0
    for j in joints_inv:
        skl_out.write(str(joint_id) + ' ' + str(' '.join(j)) + '\n')
        joint_id += 1

    # vertex_id joint_id weight
    skl_out.write('weights ' + str(len(weights)) + '\n')
    for w in weights:
        skl_out.write(str(w['vertex_id']) + ' ' + str(w['joint_id']) + ' ' + str(w['weight']) + '\n')

    skl_out.close()

# ----------------- EXPORT ANM ----------------- #
def export_anm(animations):
    anm_out = open(OUTPUT_NAME + '.anm', 'w')

    # duration
    # anm_out.write('duration ' + animations['duration'] + '\n')

    # keyframes list
    anm_out.write('keyframes\n' + '\n'.join(animations['keyframes']) + '\n')

    # joint_id keyframe_id transform
    # anm_out.write('animations\n')
    res = []
    for k in animations['keyframes']:
        res.append([])

    for a in animations['animations']:
        keyframe_id = 0
        for t in a['transforms']:
            line = str(a['joint_id']) + ' ' + ' '.join(t) + '\n'
            res[keyframe_id].append(line)
            keyframe_id += 1
    
    for i in range(len(res)):
        anm_out.write('time ' + str(i) + '\n')
        for d in res[i]:
            anm_out.write(d) 

    anm_out.close()

# ----------------- MAIN ----------------- #
geometry = extract_geometry()
materials = extract_materials()
export_obj(geometry, materials)

joints = extract_joints()
joints_inv = extract_inv_joints()

weights = extract_vertex_weights()
skeleton = extract_skeleton(joints)
export_skl(weights, skeleton, joints_inv)

animations = extract_animations(joints)
export_anm(animations)
